#!/usr/bin/python
#
# Your use of the odrive agent is provided "as is". odrive disclaims all warranties, whether express or implied,
# including without limitation, warranties that the odrive agent is merchantable and fit for your particular purposes.
#
from __future__ import print_function, unicode_literals
import argparse
import json
import os
import platform
import signal
import subprocess
import socket
import sys
import time
import codecs

if sys.version_info < (3, 0):
   sys.stdout = codecs.getwriter("utf-8")(sys.stdout)
   sys.stdin = codecs.getreader("utf-8")(sys.stdin)
else:
   unicode=str

DESCRIPTION = "odrive Make Cloud Storage THE WAY IT SHOULD BE."
URL = "https://www.odrive.com"
NO_ARGS = "Use the -h option for help."
INVALID_OPTION = "Invalid option, use -h for help"
REQUIRES_ODRIVE = "You must have odrive agent or desktop running before using this script."
ERROR_SENDING_COMMAND = "There was an error sending the command, please make sure odrive agent or desktop is running."
HOST = '127.0.0.1'
PROTOCOL_SERVER_PORT_KEY = 'protocol'
IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"
MAX_LINE_LENGTH = 80
LINE_CLEAR_CONTROL_CODE = ' ' * (MAX_LINE_LENGTH - 1) + '\r' if IS_WINDOWS else '\x1b[2K'

if IS_WINDOWS:
    from ctypes import windll, byref, Structure, c_int, c_short, c_ushort, c_byte, c_long, c_wchar_p, \
        create_unicode_buffer

    INVALID_HANDLE = -1
    STD_OUT_HANDLE = -11
    STD_ERR_HANDLE = -12
    CSIDL_PROFILE = 40
    _EightBytes = c_byte * 8


    class COORD(Structure):
        _fields_ = [("X", c_short),
                    ("Y", c_short)]


    class SMALL_RECT(Structure):
        _fields_ = [("Left", c_short),
                    ("Right", c_short),
                    ("Top", c_short),
                    ("Bottom", c_short)]


    class CONSOLE_SCREEN_BUFFER_INFO(Structure):
        _fields_ = [("dwSize", COORD),
                    ("dwCursorPosition", COORD),
                    ("wAttributes", c_ushort),
                    ("srWindow", SMALL_RECT),
                    ("dwMaximumWindowSize", COORD)]


    class GUID(Structure):
        _fields_ = [
            ("Data1", c_long),
            ("Data2", c_short),
            ("Data3", c_short),
            ("Data4", _EightBytes)
        ]


    FOLDERID_Profile = GUID(
        0x5E6C858F,
        0x0E22,
        0x4760,
        _EightBytes(0x9A, 0xFE, 0xEA, 0x33, 0x17, 0xB6, 0x71, 0x73)
    )


class OdriveCommand(object):
    def __init__(self, agentPort, desktopPort):
        self._agentPort = agentPort
        self._desktopPort = desktopPort

    def execute(self):
        sock = self._get_socket(self._agentPort) or self._get_socket(self._desktopPort)
        if sock:
            try:
                commandData = self._get_command_data()
                sock.sendall((json.dumps(commandData) + '\n').encode('utf-8'))
                return True
            except Exception as e:
                print(e)
                return False
            finally:
                sock.close()
        return False

    def _get_socket(self, port):
        if port:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                # Since we try agent first, then desktop, timeout the connect attempt quickly (100ms)
                # Otherwise commands to the desktop clients end up incurring an additional 1000ms delay for
                # connect timeout. Once connected, set timeout back to None (default)
                sock.settimeout(0.1)
                sock.connect((HOST, port))
                sock.settimeout(None)
                return sock
            except Exception as e:
                pass
        return None

    def _get_command_data(self):
        raise NotImplementedError


class OdriveSynchronousCommand(OdriveCommand):
    _RESPONSE_DATA_MAX_CHUNK_SIZE = 1024 * 1024
    _ERROR_MESSAGE = 'Error'
    _STATUS_MESSAGE = 'Status'
    _TEXT_COLOR_CYAN = 0x0003 if IS_WINDOWS else '\033[96m'
    _TEXT_COLOR_MAGENTA = 0x0005 if IS_WINDOWS else '\033[95m'
    _TEXT_COLOR_RED = 0x0004 if IS_WINDOWS else '\033[91m'
    _END_COLOR = '\033[0m'
    _FG_COLOR_INTENSE = 0x0008

    def __init__(self, agentPort, desktopPort):
        super(OdriveSynchronousCommand, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def execute(self):
        sock = self._get_socket(self._agentPort) or self._get_socket(self._desktopPort)
        if sock:

            def exit_function():
                sock.close()
                sys.exit(0)

            signal.signal(signal.SIGINT, lambda signum, frame: exit_function())
            signal.signal(signal.SIGTERM, lambda signum, frame: exit_function())

            try:
                sock.sendall((json.dumps(self._get_command_data()) + '\n').encode('utf-8'))
                receivedStatusMessage = False
                lastMessageType = None
                for messageType, message in self._read_responses(sock):
                    self._print_response(messageType, message)
                    if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
                        receivedStatusMessage = True
                    lastMessageType = messageType

                self._print_final_response(lastMessageType, receivedStatusMessage)
                return True
            except Exception as e:
                print(e)
                return False
            finally:
                sock.close()
        return False

    def _read_responses(self, sock):
        data = True
        buff = ''

        while data:
            data = sock.recv(OdriveSynchronousCommand._RESPONSE_DATA_MAX_CHUNK_SIZE)
            buff += data.decode('utf-8')
            while buff.find('\n') != -1:
                response, buff = buff.split('\n', 1)
                jsonResponse = json.loads(response)
                yield jsonResponse.get('messageType'), jsonResponse.get('message')

    def _supports_color(self):
        if IS_LINUX:
            try:
                return int(subprocess.check_output('tput colors', shell=True).strip('\n')) > 0
            except Exception as e:
                return False
        else:
            return True

    def _output_message(self, message, stderr=False, color=None):
        if not message:
            return
        if IS_WINDOWS:
            if (stderr and sys.stderr.isatty()) or ((not stderr) and sys.stdout.isatty()):
                # if we are writing to the console in windows we need to use WriteConsoleW for unicode output
                handle = windll.kernel32.GetStdHandle(STD_ERR_HANDLE if stderr else STD_OUT_HANDLE)
                if handle and handle != INVALID_HANDLE:
                    chars_written = c_int(0)
                    if color:
                        consoleInfo = CONSOLE_SCREEN_BUFFER_INFO()
                        windll.kernel32.GetConsoleScreenBufferInfo(handle, byref(consoleInfo))
                        origionalConsoleColors = consoleInfo.wAttributes
                        origionalBackgroundColor = origionalConsoleColors & 0x0070
                        newColors = color | origionalBackgroundColor | OdriveSynchronousCommand._FG_COLOR_INTENSE
                        windll.kernel32.SetConsoleTextAttribute(handle, newColors)
                        windll.kernel32.WriteConsoleW(handle, message, len(message), byref(chars_written), None)
                        windll.kernel32.SetConsoleTextAttribute(handle, origionalConsoleColors)
                    else:
                        windll.kernel32.WriteConsoleW(handle, message, len(message), byref(chars_written), None)
                    return
        if stderr:
            if color and sys.stderr.isatty() and not IS_WINDOWS:
                sys.stderr.write('{}{}{}'.format(color, message, OdriveSynchronousCommand._END_COLOR))
            else:
                sys.stderr.write(message)
            sys.stderr.flush()
        else:
            if color and sys.stdout.isatty() and not IS_WINDOWS:
                sys.stdout.write('{}{}{}'.format(color, message, OdriveSynchronousCommand._END_COLOR))
            else:
                sys.stdout.write(message)
            sys.stdout.flush()

    def _print_response(self, messageType, message):
        try:
            if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
                self._output_message('{}\n'.format(message))
            elif messageType == OdriveSynchronousCommand._ERROR_MESSAGE:
                self._output_message('{}\n'.format(message), stderr=True)
        except Exception as e:
            pass

    def _print_final_response(self, lastMessageType, receivedStatusMessge):
        pass

    def _get_command_data(self):
        raise NotImplementedError


class Stream(OdriveCommand):
    COMMAND_NAME = 'stream'
    HELP = "stream placholder/remote file eg. stream path | app - \n or stream to a file eg. stream path > file.ext"
    PATH_ARGUMENT_HELP = "the path to the placeholder file or a remote path"
    PATH_ARGUMENT_NAME = "path"
    _STREAMING_CHUNK_SIZE = 256 * 1024

    def __init__(self, agentPort, desktopPort, path):
        super(Stream, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._path = path

    def _get_command_data(self):
        return {
            'command': Stream.COMMAND_NAME,
            'parameters': {
                Stream.PATH_ARGUMENT_NAME: self._path
            }
        }

    def execute(self):
        sock = self._get_socket(self._agentPort) or self._get_socket(self._desktopPort)
        if sock:

            def exit_function():
                sock.close()
                sys.exit(0)

            signal.signal(signal.SIGINT, lambda signum, frame: exit_function())
            signal.signal(signal.SIGTERM, lambda signum, frame: exit_function())

            try:
                sock.sendall((json.dumps(self._get_command_data()) + '\n').encode('utf-8'))

                if sys.version_info < (3,):
                    if IS_WINDOWS:
                        import msvcrt
                        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
                    outputStream = sys.stdout
                else:
                    outputStream = sys.stdout.buffer

                while True:
                    data = sock.recv(Stream._STREAMING_CHUNK_SIZE)
                    if data:
                        outputStream.write(data)
                        outputStream.flush()
                    else:
                        return True
            except Exception as e:
                return False
            finally:
                sock.close()
        return False


class StreamRemote(Stream):
    COMMAND_NAME = 'streamremote'
    HELP = "use a remote path instead of a local placeholder path. eg. /Dropbox/movie.mp4"
    STREAM_REMOTE_ARGUMENT_NAME = "--remote"
    PATH_ARGUMENT_NAME = "path"

    def __init__(self, agentPort, desktopPort, path):
        super(StreamRemote, self).__init__(agentPort=agentPort, desktopPort=desktopPort, path=path)

    def _get_command_data(self):
        return {
            'command': StreamRemote.COMMAND_NAME,
            'parameters': {
                StreamRemote.PATH_ARGUMENT_NAME: self._path
            }
        }


class Authenticate(OdriveSynchronousCommand):
    COMMAND_NAME = 'authenticate'
    HELP = "authenticate odrive with an auth key"
    AUTH_KEY_ARGUMENT_NAME = 'authKey'
    AUTH_KEY_ARGUMENT_HELP = "auth key obtained from {}".format(URL)

    def __init__(self, agentPort, desktopPort, authKey):
        super(Authenticate, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._authKey = authKey

    def _get_command_data(self):
        return {
            'command': Authenticate.COMMAND_NAME,
            'parameters': {
                Authenticate.AUTH_KEY_ARGUMENT_NAME: self._authKey
            }
        }


class Deauthorize(OdriveCommand):
    COMMAND_NAME = 'deauthorize'
    HELP = "deauthorize odrive to unlink the current user and exit"

    def __init__(self, agentPort, desktopPort):
        super(Deauthorize, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _get_command_data(self):
        return {
            'command': Deauthorize.COMMAND_NAME,
            'parameters': {
            }
        }


class Diagnostics(OdriveSynchronousCommand):
    COMMAND_NAME = 'diagnostics'
    HELP = "generate diagnostics"

    def __init__(self, agentPort, desktopPort):
        super(Diagnostics, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _get_command_data(self):
        return {
            'command': Diagnostics.COMMAND_NAME,
            'parameters': {
            }
        }


class XLThreshold(OdriveCommand):
    COMMAND_NAME = 'xlthreshold'
    HELP = "split files larger than this threshold"
    THRESHOLD_ARGUMENT_NAME = 'threshold'
    THRESHOLD_ARGUMENT_HELP = "choose from never, small (100MB), medium (500MB), large (1GB), xlarge (2GB)"
    THRESHOLD_ARGUMENT_VALUES = ['never', 'small', 'medium', 'large', 'xlarge']

    def __init__(self, agentPort, desktopPort, threshold):
        super(XLThreshold, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._threshold = threshold

    def _get_command_data(self):
        return {
            'command': XLThreshold.COMMAND_NAME,
            'parameters': {
                XLThreshold.THRESHOLD_ARGUMENT_NAME: self._threshold
            }
        }

class AutoUnsyncThreshold(OdriveCommand):
    COMMAND_NAME = 'autounsyncthreshold'
    HELP = "Set rule for automatically unsyncing files that have not been modified with a certain amount of time"
    THRESHOLD_ARGUMENT_NAME = 'threshold'
    THRESHOLD_ARGUMENT_HELP = "choose from never, daily (day), weekly (week), monthly (month)"
    THRESHOLD_ARGUMENT_VALUES = ['never', 'day', 'week', 'month']

    def __init__(self, agentPort, desktopPort, threshold):
        super(AutoUnsyncThreshold, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._threshold = threshold

    def _get_command_data(self):
        return {
            'command': AutoUnsyncThreshold.COMMAND_NAME,
            'parameters': {
                AutoUnsyncThreshold.THRESHOLD_ARGUMENT_NAME: self._threshold
            }
        }

class AutoTrashThreshold(OdriveCommand):
    COMMAND_NAME = 'autotrashthreshold'
    HELP = "Set rule for automatically emptying the odrive trash"
    THRESHOLD_ARGUMENT_NAME = 'threshold'
    THRESHOLD_ARGUMENT_HELP = "choose from never, immediately, every 15 minutes (fifteen), hourly (hour), daily (day)"
    THRESHOLD_ARGUMENT_VALUES = ['never', 'immediately', 'fifteen', 'hour', 'day']

    def __init__(self, agentPort, desktopPort, threshold):
        super(AutoTrashThreshold, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._threshold = threshold

    def _get_command_data(self):
        return {
            'command': AutoTrashThreshold.COMMAND_NAME,
            'parameters': {
                AutoTrashThreshold.THRESHOLD_ARGUMENT_NAME: self._threshold
            }
        }

class PlaceholderThreshold(OdriveCommand):
    COMMAND_NAME = 'placeholderthreshold'
    HELP = "Set rule for automatically downloading files within a certain size when syncing/expanding a folder"
    THRESHOLD_ARGUMENT_NAME = 'threshold'
    THRESHOLD_ARGUMENT_HELP = "choose from never, small (10MB), medium (100MB), large (500MB), always"
    THRESHOLD_ARGUMENT_VALUES = ['never', 'small', 'medium', 'large', 'always']

    def __init__(self, agentPort, desktopPort, threshold):
        super(PlaceholderThreshold, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._threshold = threshold

    def _get_command_data(self):
        return {
            'command': PlaceholderThreshold.COMMAND_NAME,
            'parameters': {
                PlaceholderThreshold.THRESHOLD_ARGUMENT_NAME: self._threshold
            }
        }

class FolderSyncRule(OdriveCommand):
    COMMAND_NAME = 'foldersyncrule'
    HELP = "Set rule for automatically syncing new remote content. This is usually used after recursively syncing a folder"
    LOCAL_PATH_ARGUMENT_NAME = "path"
    LOCAL_PATH_ARGUMENT_HELP = "The local path of the folder to apply the rule to."
    THRESHOLD_ARGUMENT_NAME = 'threshold'
    THRESHOLD_ARGUMENT_HELP = "Size in MB (base 10) for the download threshold. Use '0' for nothing and 'inf' for infinite. Files that have a size under this will be downloaded."
    EXPAND_SUBFOLDERS_ARGUMENT_NAME = 'expandsubfolders'
    EXPAND_SUBFOLDERS_ARGUMENT_HELP = 'Apply this rule to files and folders underneath the specified folder.'

    def __init__(self, agentPort, desktopPort, path, threshold, expandSubfolders):
        super(FolderSyncRule, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._path = path
        self._threshold = threshold
        self._expandSubfolders = expandSubfolders

    def _get_command_data(self):
        newFolderPath = make_unicode(self._path)
        if not os.path.exists(get_os_encoded_path(newFolderPath)):
            output_message(u'{}\n'.format(newFolderPath + u" doesn't exist!"))
            return True
        if not os.path.isdir(get_os_encoded_path(newFolderPath)):
            output_message(u'{}\n'.format(newFolderPath + u" is not a folder"))
            return True
        if not (unicode(self._threshold).isnumeric() or self._threshold == 'inf'):
            output_message('{}\n'.format(u"Invalid threshold specified"))
            return True
        return {
            'command': FolderSyncRule.COMMAND_NAME,
            'parameters': {
                FolderSyncRule.LOCAL_PATH_ARGUMENT_NAME: self._path,
                FolderSyncRule.THRESHOLD_ARGUMENT_NAME: self._threshold,
                FolderSyncRule.EXPAND_SUBFOLDERS_ARGUMENT_NAME: self._expandSubfolders
            }
        }

class EncPassphrase(OdriveSynchronousCommand):
    COMMAND_NAME = 'encpassphrase'
    HELP = "specify a passphrase for Encryptor folders"
    PASSPHRASE_ARGUMENT_NAME = 'passphrase'
    PASSPHRASE_ARGUMENT_HELP = "Encryptor folder passphrase"
    ID_ARGUMENT_NAME = 'id'
    ID_ARGUMENT_HELP = "Encryptor ID"
    INITIALIZE_ARGUMENT_NAME = 'initialize'
    INITIALIZE_ARGUMENT_HELP = "Initialize a new Encryptor folder passphrase. Do not use if passphrase has already been set"

    def __init__(self, agentPort, desktopPort, passphrase, id, initialize):
        super(EncPassphrase, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._passphrase = passphrase
        self._id = id
        self._initialize = initialize

    def _get_command_data(self):
        return {
            'command': EncPassphrase.COMMAND_NAME,
            'parameters': {
                EncPassphrase.PASSPHRASE_ARGUMENT_NAME: self._passphrase,
                EncPassphrase.ID_ARGUMENT_NAME: self._id,
                EncPassphrase.INITIALIZE_ARGUMENT_NAME: self._initialize
            }
        }

class BackupNow(OdriveSynchronousCommand):
    COMMAND_NAME = 'backupnow'
    HELP = "run backup jobs immediately"

    def __init__(self, agentPort, desktopPort):
        super(BackupNow, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _get_command_data(self):
        return {
            'command': BackupNow.COMMAND_NAME,
            'parameters': {
            }
        }

class Mount(OdriveSynchronousCommand):
    COMMAND_NAME = 'mount'
    HELP = "mount remote odrive path to a local folder"
    LOCAL_PATH_ARGUMENT_HELP = "local path of the desired mount folder"
    LOCAL_PATH_ARGUMENT_NAME = "localPath"
    REMOTE_PATH_ARGUMENT_HELP = "remote path of the mount i.e. /Google Drive/Pictures or just / for the odrive root"
    REMOTE_PATH_ARGUMENT_NAME = "remotePath"

    def __init__(self, agentPort, desktopPort, localPath, remotePath):
        super(Mount, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._localPath = localPath
        self._remotePath = remotePath

    def _get_command_data(self):
        return {
            'command': Mount.COMMAND_NAME,
            'parameters': {
                Mount.LOCAL_PATH_ARGUMENT_NAME: self._localPath,
                Mount.REMOTE_PATH_ARGUMENT_NAME: self._remotePath
            }
        }


class Unmount(OdriveSynchronousCommand):
    COMMAND_NAME = 'unmount'
    HELP = "remove a mount"
    LOCAL_PATH_ARGUMENT_HELP = "local path of the mount"
    LOCAL_PATH_ARGUMENT_NAME = "localPath"

    def __init__(self, agentPort, desktopPort, localPath):
        super(Unmount, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._localPath = localPath

    def _get_command_data(self):
        return {
            'command': Unmount.COMMAND_NAME,
            'parameters': {
                Unmount.LOCAL_PATH_ARGUMENT_NAME: self._localPath,
            }
        }


class Backup(OdriveSynchronousCommand):
    COMMAND_NAME = 'backup'
    HELP = "backup a local folder to a remote odrive path"
    LOCAL_PATH_ARGUMENT_HELP = "local path of the desired backup folder"
    LOCAL_PATH_ARGUMENT_NAME = "localPath"
    REMOTE_PATH_ARGUMENT_HELP = "remote path of the backup i.e. /Amazon Cloud Drive/Backup"
    REMOTE_PATH_ARGUMENT_NAME = "remotePath"

    def __init__(self, agentPort, desktopPort, localPath, remotePath):
        super(Backup, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._localPath = localPath
        self._remotePath = remotePath

    def _get_command_data(self):
        return {
            'command': Backup.COMMAND_NAME,
            'parameters': {
                Backup.LOCAL_PATH_ARGUMENT_NAME: self._localPath,
                Backup.REMOTE_PATH_ARGUMENT_NAME: self._remotePath
            }
        }


class RemoveBackup(OdriveSynchronousCommand):
    COMMAND_NAME = 'removebackup'
    HELP = "remove a backup job"
    BACKUP_ID_ARGUMENT_HELP = "The ID of the backup. Use 'status --backups' to list existing backups"
    BACKUP_ID_ARGUMENT_NAME = "backupId"

    def __init__(self, agentPort, desktopPort, backupId):
        super(RemoveBackup, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._backupId = backupId

    def _get_command_data(self):
        return {
            'command': RemoveBackup.COMMAND_NAME,
            'parameters': {
                RemoveBackup.BACKUP_ID_ARGUMENT_NAME: self._backupId,
            }
        }


class Sync(OdriveSynchronousCommand):
    COMMAND_NAME = 'sync'
    HELP = "sync a placeholder"
    PLACEHOLDER_PATH_ARGUMENT_HELP = "the path to the placeholder file"
    PLACEHOLDER_PATH_ARGUMENT_NAME = "placeholderPath"

    def __init__(self, agentPort, desktopPort, placeholderPath):
        super(Sync, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._placeholderPath = placeholderPath

    def _get_command_data(self):
        return {
            'command': Sync.COMMAND_NAME,
            'parameters': {
                Sync.PLACEHOLDER_PATH_ARGUMENT_NAME: self._placeholderPath
            }
        }

    def _print_response(self, messageType, message):
        try:
            if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
                if sys.stdout.isatty():
                    # clear current line and update status
                    self._output_message('\r{}{}'.format(LINE_CLEAR_CONTROL_CODE, message))
                else:
                    self._output_message('{}\n'.format(message))
            elif messageType == OdriveSynchronousCommand._ERROR_MESSAGE:
                # clear line before writing message in case status message present(happens if stdout == stderr)
                if sys.stderr.isatty():
                    self._output_message('\r{}{}\n'.format(LINE_CLEAR_CONTROL_CODE, message), stderr=True)
                else:
                    self._output_message('{}\n'.format(message), stderr=True)
        except Exception as e:
            pass

    def _print_final_response(self, lastMessageType, receivedStatusMessge):
        try:
            if sys.stdout.isatty() and receivedStatusMessge and \
                    lastMessageType == OdriveSynchronousCommand._STATUS_MESSAGE:
                # no newline on status messages so bump to next line before exit
                self._output_message('\n')
        except Exception as e:
            pass


class SyncAsynchronous(OdriveCommand):
    COMMAND_NAME = 'sync'
    HELP = "sync a placeholder"
    PLACEHOLDER_PATH_ARGUMENT_HELP = "the path to the placeholder file"
    PLACEHOLDER_PATH_ARGUMENT_NAME = "placeholderPath"

    def __init__(self, agentPort, desktopPort, placeholderPath):
        super(SyncAsynchronous, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._placeholderPath = placeholderPath

    def _get_command_data(self):
        return {
            'command': SyncAsynchronous.COMMAND_NAME,
            'parameters': {
                Sync.PLACEHOLDER_PATH_ARGUMENT_NAME: self._placeholderPath
            }
        }


class RecursiveSync(object):
    COMMAND_NAME = "recursive"
    HELP = "recursively sync"
    NO_DOWNLOAD_ARGUMENT_HELP = "do not download (used with --recursive)"
    NO_DOWNLOAD_ARGUMENT_NAME = "nodownload"
    # Hidden argument to send commands to the sync engine asynchronously (experimental)
    NO_WAIT_ARGUMENT_NAME = 'nowait'

    def __init__(self, agentPort, desktopPort, folderPath, noDownload, noWait=False):
        self.agentPort = agentPort
        self.desktopPort = desktopPort
        self.folderPath = folderPath
        self.noDownload = noDownload
        # Set async or sync
        self.noWait = noWait

    def execute(self):
        newFolderPath = make_unicode(self.folderPath)
        if not os.path.exists(get_os_encoded_path(newFolderPath)):
            output_message('{}\n'.format(newFolderPath + u" doesn't exist!"))
            return True
        itemsRemain = 1
        if newFolderPath.endswith((u'.cloud', u'.cloudf', u'.cloud-dev', u'.cloudf-dev')):
            if self.noWait:
                output_message(u'Syncing {}\n'.format(newFolderPath))
                command = SyncAsynchronous(agentPort=self.agentPort,
                               desktopPort=self.desktopPort,
                               placeholderPath=newFolderPath)
            else:
                command = Sync(agentPort=self.agentPort,
                            desktopPort=self.desktopPort,
                            placeholderPath=newFolderPath)
            if newFolderPath.endswith((u'.cloudf', u'.cloudf-dev')):
                newFolderPath = os.path.splitext(newFolderPath)[0]
            else:
                itemsRemain = 0
            success = command.execute()
            if not success:
                output_message('{}\n'.format(ERROR_SENDING_COMMAND))
                sys.exit(1)
        lastFilesRemain = 0
        lastPath = u''
        retries = 0
        newPath = None
        if self.noWait:
            # Need a slight delay because of the async comm
            time.sleep(1)
        while itemsRemain:
            if self.noWait:
                # Need a slight delay because of the async comm
                time.sleep(1)
            itemsRemain = 0
            for root, dirs, files in os.walk(get_os_encoded_path(newFolderPath)):
                root = make_unicode(root)
                for f in sorted(files):  # Sort so that we always traverse the same way
                    newPath = None
                    f = make_unicode(f)
                    if f.endswith((u'.cloudf', u'.cloudf-dev')) or (f.endswith((u'.cloud', u'.cloud-dev')) and not self.noDownload):
                        itemsRemain += 1
                        if sys.platform.startswith('win32'):
                            newPath = os.path.join(root, f)[4:]  # odrive does its own prefixing, so remove it if on Win
                        else:
                            newPath = os.path.join(root, f)
                        if self.noWait:
                            output_message(u'Syncing {}\n'.format(newPath))
                            command = SyncAsynchronous(agentPort=self.agentPort,
                                                         desktopPort=self.desktopPort,
                                                         placeholderPath=newPath)
                        else:
                            command = Sync(agentPort=self.agentPort,
                                           desktopPort=self.desktopPort,
                                           placeholderPath=newPath)
                        success = command.execute()
                        if not success:
                            output_message('{}\n'.format(ERROR_SENDING_COMMAND))
                            sys.exit(1)
            if lastFilesRemain == itemsRemain and newPath and lastPath == newPath:
                # If we have the same number of unsynced items as we did on the last pass
                # and the final item attempted was the same as before, then we did not make any progress
                # Retry 5 times and then give up
                if retries > 4:
                    output_message(u'Done with recursive sync of {}. Unable to sync {} items\n'.format(newFolderPath, itemsRemain))
                    sys.exit(1)
                retries += 1
            else:
                retries = 0
            lastPath = newPath
            lastFilesRemain = itemsRemain
        output_message(u'Done with recursive sync of {}\n'.format(newFolderPath))
        return True


class Refresh(OdriveSynchronousCommand):
    COMMAND_NAME = 'refresh'
    HELP = "refresh a folder"
    FOLDER_PATH_ARGUMENT_HELP = "path of the folder to refresh"
    FOLDER_PATH_ARGUMENT_NAME = "folderPath"

    def __init__(self, agentPort, desktopPort, folderPath):
        super(Refresh, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._folderPath = folderPath

    def _get_command_data(self):
        return {
            'command': Refresh.COMMAND_NAME,
            'parameters': {
                Refresh.FOLDER_PATH_ARGUMENT_NAME: self._folderPath
            }
        }

    def _get_color_for_sync_state(self, syncState):
        if syncState == 'Synced' or syncState == 'Locked':
            return OdriveSynchronousCommand._TEXT_COLOR_CYAN
        elif syncState == 'Active':
            return OdriveSynchronousCommand._TEXT_COLOR_MAGENTA
        else:
            return None

    def _print_response(self, messageType, message):
        try:
            if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
                jsonResponse = json.loads(message)
                syncState = jsonResponse.get('syncState')
                if syncState:
                    supportsColor = self._supports_color()
                    self._output_message('{}\n'.format(syncState),
                                         color=self._get_color_for_sync_state(syncState) if supportsColor else None)

                    childSyncStates = jsonResponse.get('childSyncStates')
                    if childSyncStates:
                        for name, syncState in childSyncStates.items():
                            if supportsColor:
                                self._output_message('{}\n'.format(name),
                                                     color=self._get_color_for_sync_state(syncState))
                            else:
                                self._output_message('{}: {}\n'.format(syncState, name))
        except Exception as e:
            pass


class Unsync(OdriveSynchronousCommand):
    COMMAND_NAME = 'unsync'
    HELP = "unsync a file or a folder"
    PATH_ARGUMENT_HELP = "file or folder path"
    PATH_ARGUMENT_NAME = "path"

    def __init__(self, agentPort, desktopPort, path):
        super(Unsync, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._path = path

    def _get_command_data(self):
        return {
            'command': Unsync.COMMAND_NAME,
            'parameters': {
                Unsync.PATH_ARGUMENT_NAME: self._path
            }
        }


class ForceUnsync(OdriveSynchronousCommand):
    COMMAND_NAME = 'forceunsync'
    HELP = "force unsync a file or a folder - permanently deleting any changes or files that have not been uploaded."
    FORCE_UNSYNC_ARGUMENT_NAME = "--force"
    PATH_ARGUMENT_NAME = "path"

    def __init__(self, agentPort, desktopPort, path):
        super(ForceUnsync, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._path = path

    def _get_command_data(self):
        return {
            'command': ForceUnsync.COMMAND_NAME,
            'parameters': {
                ForceUnsync.PATH_ARGUMENT_NAME: self._path
            }
        }


class SyncState(OdriveSynchronousCommand):
    COMMAND_NAME = 'syncstate'
    HELP = "get sync status info"
    PATH_ARGUMENT_HELP = "file or folder path"
    PATH_ARGUMENT_NAME = "path"
    TEXTONLY_ARGUMENT_HELP = "display file and folder states with text rather than color"
    TEXTONLY_ARGUMENT_NAME = '--textonly'

    def __init__(self, agentPort, desktopPort, path, textonly):
        super(SyncState, self).__init__(agentPort=agentPort, desktopPort=desktopPort)
        self._path = path
        self._textonly = textonly

    def _get_command_data(self):
        return {
            'command': SyncState.COMMAND_NAME,
            'parameters': {
                SyncState.PATH_ARGUMENT_NAME: self._path
            }
        }

    def _get_color_for_sync_state(self, syncState):
        if syncState == 'Synced' or syncState == 'Locked':
            return OdriveSynchronousCommand._TEXT_COLOR_CYAN
        elif syncState == 'Active':
            return OdriveSynchronousCommand._TEXT_COLOR_MAGENTA
        else:
            return None

    def _print_response(self, messageType, message):
        try:
            if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
                jsonResponse = json.loads(message)
                syncState = jsonResponse.get('syncState')
                if syncState:
                    if self._textonly:
                        supportsColor = False
                    else:
                        supportsColor = self._supports_color()
                    self._output_message('{}\n'.format(syncState),
                                         color=self._get_color_for_sync_state(syncState) if supportsColor else None)

                    childSyncStates = jsonResponse.get('childSyncStates')
                    if childSyncStates:
                        for name, syncState in childSyncStates.items():
                            if supportsColor:
                                self._output_message('{}\n'.format(name),
                                                     color=self._get_color_for_sync_state(syncState))
                            else:
                                self._output_message('{}: {}\n'.format(syncState, name))
        except Exception as e:
            pass


class Status(OdriveSynchronousCommand):
    COMMAND_NAME = 'status'
    HELP = "get status info"

    def __init__(self, agentPort, desktopPort):
        super(Status, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _get_command_data(self):
        return {
            'command': Status.COMMAND_NAME,
            'parameters': {
            }
        }

    def _clear_tty(self):
        if sys.stdout.isatty():
            if IS_WINDOWS:
                _ = subprocess.call('cls', shell=True)
            else:
                _ = subprocess.call('clear', shell=True)

    def _print_left_and_right_justified(self, left, right):
        self._output_message('{}{}{}\n'.format(left, ' ' * (MAX_LINE_LENGTH - (len(left + right))), right))

    def _print_response(self, messageType, message):
        if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
            try:
                supportsColor = self._supports_color()
                self._clear_tty()
                self._output_message(DESCRIPTION + '\n\n',
                                     color=OdriveSynchronousCommand._TEXT_COLOR_MAGENTA if supportsColor else None)
                self._print_left_and_right_justified('isActivated: {}'.format(message.get('isActivated')),
                                                     'hasSession: {}'.format(message.get('hasSession')))
                self._print_left_and_right_justified('email: {}'.format(message.get('authorizedEmail')),
                                                     'accountType: {}'.format(message.get(
                                                         'authorizedAccountSourceType')))
                self._print_left_and_right_justified('syncEnabled: {}'.format(message.get('syncEnabled')),
                                                     'version: {}'.format(message.get('productVersion')))
                self._print_left_and_right_justified('placeholderThreshold: {}'.format(message.get(
                    'placeholderThreshold')),
                    'autoUnsyncThreshold: {}'.format(message.get(
                        'autoUnsyncThreshold')))
                self._print_left_and_right_justified('downloadThrottlingThreshold: {}'.format(
                    message.get(
                        'downloadThrottlingThreshold')),
                    'uploadThrottlingThreshold: {}'.format(
                        message.get(
                            'uploadThrottlingThreshold')))
                numMounts = len(message.get('proSyncFolders')) + (1 if message.get('odriveFolder')["path"] else 0)
                self._print_left_and_right_justified('autoTrashThreshold: {}'.format(message.get('autoTrashThreshold')),
                                                     'Mounts: {}'.format(numMounts))
                self._print_left_and_right_justified('xlThreshold: {}'.format(message.get('xlFileThreshold')),
                                                     'Backups: {}'.format(len(message.get('backupJobs'))))
                self._output_message('\n')

                numSyncRequests = len(message.get('expandRequests')) + len(message.get('syncRequests'))
                numBackgroundRequests = len(message.get('refreshChildOperations'))
                numUploads = len(message.get('uploads'))
                numDownloads = len(message.get('downloads'))
                numTrash = len(message.get('trashItems'))
                numWaiting = len(message.get('waitingItems'))
                numNotAllowed = len(message.get('notAllowedItems'))

                self._output_message('Sync Requests: {}\n'.format(numSyncRequests),
                                     color=OdriveSynchronousCommand._TEXT_COLOR_MAGENTA if
                                     numSyncRequests and supportsColor else None)
                self._output_message('Background Requests: {}\n'.format(numBackgroundRequests),
                                     color=OdriveSynchronousCommand._TEXT_COLOR_MAGENTA if
                                     numBackgroundRequests and supportsColor else None)
                self._output_message('Uploads: {}\n'.format(numUploads),
                                     color=OdriveSynchronousCommand._TEXT_COLOR_MAGENTA if
                                     numUploads and supportsColor else None)
                self._output_message('Downloads: {}\n'.format(numDownloads),
                                     color=OdriveSynchronousCommand._TEXT_COLOR_MAGENTA if
                                     numDownloads and supportsColor else None)
                self._output_message('Trash: {}\n'.format(numTrash))
                self._output_message('Waiting: {}\n'.format(numWaiting))
                self._output_message('Not Allowed: {}\n'.format(numNotAllowed),
                                     color=OdriveSynchronousCommand._TEXT_COLOR_RED if
                                     numNotAllowed and supportsColor else None)

                self._output_message('\n')
            except Exception as e:
                pass


class MountsStatus(Status):
    HELP = 'get status on mounts'
    MOUNTS_STATUS_ARGUMENT_NAME = '--mounts'

    def __init__(self, agentPort, desktopPort):
        super(MountsStatus, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _print_response(self, messageType, message):
        if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
            try:
                mounts = message.get('proSyncFolders')
                odriveFolder = message.get('odriveFolder')
                if mounts:
                    for mount in mounts:
                        path = mount.get('path')
                        status = mount.get('status')
                        self._output_message('{}  status:{}\n'.format(path, status))
                if odriveFolder:
                    path = odriveFolder.get('path')
                    status = odriveFolder.get('status')
                    self._output_message('{}  status:{}\n'.format(path, status))
                if not (mounts or odriveFolder):
                    self._output_message('No mounts.\n')
            except Exception as e:
                pass


class BackupsStatus(Status):
    HELP = 'get status on backup jobs'
    BACKUPS_STATUS_ARGUMENT_NAME = '--backups'

    def __init__(self, agentPort, desktopPort):
        super(BackupsStatus, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _print_response(self, messageType, message):
        if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
            try:
                backups = message.get('backupJobs')
                if backups:
                    for backup in backups:
                        localPath = backup.get('localPath')
                        remotePath = backup.get('remotePath')
                        status = backup.get('status')
                        backupId = backup.get('jobId')
                        self._output_message('\nID: {}\nLocal Path: {}\nRemote Path: {}\nStatus: {}\n\n'.format(backupId, localPath, remotePath, status))
                else:
                    self._output_message('No backup jobs.\n')
            except Exception as e:
                pass


class SyncRequestsStatus(Status):
    HELP = 'get status on sync requests'
    SYNC_REQUESTS_STATUS_ARGUMENT_NAME = '--sync_requests'

    def __init__(self, agentPort, desktopPort):
        super(SyncRequestsStatus, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _print_response(self, messageType, message):
        if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
            try:
                syncRequests = message.get('expandRequests') + message.get('syncRequests')
                if syncRequests:
                    for syncRequest in syncRequests:
                        name = syncRequest.get('path') if syncRequest.get('path') else syncRequest.get('firstPathItem')
                        percentComplete = syncRequest.get('percentComplete')
                        self._output_message('{} {}%\n'.format(name, percentComplete))
                else:
                    self._output_message('No active sync requests.\n')
            except Exception as e:
                pass


class BackgroundStatus(Status):
    HELP = 'get status on background requests'
    BACKGROUND_STATUS_ARGUMENT_NAME = '--background'

    def __init__(self, agentPort, desktopPort):
        super(BackgroundStatus, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _print_response(self, messageType, message):
        if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
            try:
                backgroundRequests = message.get('refreshChildOperations')
                if backgroundRequests:
                    for backgroundRequest in backgroundRequests:
                        name = backgroundRequest.get('name')
                        percentComplete = backgroundRequest.get('percentComplete')
                        self._output_message('{} {}%\n'.format(name, percentComplete))
                else:
                    self._output_message('No active background requests.\n')
            except Exception as e:
                pass


class UploadsStatus(Status):
    HELP = 'get status on uploads'
    UPLOADS_STATUS_ARGUMENT_NAME = '--uploads'

    def __init__(self, agentPort, desktopPort):
        super(UploadsStatus, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _print_response(self, messageType, message):
        if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
            try:
                uploads = message.get('uploads')
                if uploads:
                    for upload in uploads:
                        name = upload.get('name')
                        uploadPath = upload.get('path')
                        percentComplete = upload.get('percentComplete')
                        self._output_message('{} {}%\n'.format(uploadPath, percentComplete))
                else:
                    self._output_message('No uploads.\n')
            except Exception as e:
                pass


class DownloadsStatus(Status):
    HELP = 'get status on downloads'
    DOWNLOADS_STATUS_ARGUMENT_NAME = '--downloads'

    def __init__(self, agentPort, desktopPort):
        super(DownloadsStatus, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _print_response(self, messageType, message):
        if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
            try:
                downloads = message.get('downloads')
                if downloads:
                    for download in downloads:
                        name = download.get('name')
                        downloadPath = download.get('path')
                        percentComplete = download.get('percentComplete')
                        self._output_message('{} {}%\n'.format(downloadPath, percentComplete))
                else:
                    self._output_message('No downloads.\n')
            except Exception as e:
                pass


class TrashStatus(Status):
    HELP = 'get status of trash items'
    TRASH_STATUS_ARGUMENT_NAME = '--trash'

    def __init__(self, agentPort, desktopPort):
        super(TrashStatus, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _print_response(self, messageType, message):
        if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
            try:
                trashItems = message.get('trashItems')
                if trashItems:
                    for trashItem in trashItems:
                        name = trashItem.get('name')
                        folderPath = trashItem.get('folderPath')
                        self._output_message('{}\n'.format(os.path.join(folderPath, name)))
                else:
                    self._output_message('No trash.\n')
            except Exception as e:
                pass


class WaitingStatus(Status):
    HELP = 'get status of waiting items'
    WAITING_STATUS_ARGUMENT_NAME = '--waiting'

    def __init__(self, agentPort, desktopPort):
        super(WaitingStatus, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _print_response(self, messageType, message):
        if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
            try:
                waitingItems = message.get('waitingItems')
                if waitingItems:
                    for waitingItem in waitingItems:
                        name = waitingItem.get('name')
                        folderPath = waitingItem.get('folderPath')
                        explanation = waitingItem.get('explanation')
                        self._output_message('{} - {}\n'.format(os.path.join(folderPath, name), explanation))
                else:
                    self._output_message('No waiting items.\n')
            except Exception as e:
                pass


class NotAllowedStatus(Status):
    HELP = 'get status of not allowed items'
    NOT_ALLOWED_STATUS_ARGUMENT_NAME = '--not_allowed'

    def __init__(self, agentPort, desktopPort):
        super(NotAllowedStatus, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _print_response(self, messageType, message):
        if messageType == OdriveSynchronousCommand._STATUS_MESSAGE:
            try:
                notAllowedItems = message.get('notAllowedItems')
                if notAllowedItems:
                    for notAllowedItem in notAllowedItems:
                        name = notAllowedItem.get('name')
                        folderPath = notAllowedItem.get('folderPath')
                        explanation = notAllowedItem.get('explanation')
                        self._output_message('{} - {}\n'.format(os.path.join(folderPath, name), explanation))
                else:
                    self._output_message('No not allowed items.\n')
            except Exception as e:
                pass


class EmptyTrash(OdriveSynchronousCommand):
    COMMAND_NAME = 'emptytrash'
    HELP = "empty odrive trash"

    def __init__(self, agentPort, desktopPort):
        super(EmptyTrash, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _get_command_data(self):
        return {
            'command': EmptyTrash.COMMAND_NAME,
            'parameters': {
            }
        }


class RestoreTrash(OdriveSynchronousCommand):
    COMMAND_NAME = 'restoretrash'
    HELP = "restore odrive trash"

    def __init__(self, agentPort, desktopPort):
        super(RestoreTrash, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _get_command_data(self):
        return {
            'command': RestoreTrash.COMMAND_NAME,
            'parameters': {
            }
        }


class Shutdown(OdriveCommand):
    COMMAND_NAME = 'shutdown'
    HELP = "shutdown odrive"

    def __init__(self, agentPort, desktopPort):
        super(Shutdown, self).__init__(agentPort=agentPort, desktopPort=desktopPort)

    def _get_command_data(self):
        return {
            'command': Shutdown.COMMAND_NAME,
            'parameters': {
            }
        }


def unicode_path(string):
    # need to strip extra quote from paths that end with a slash for windows
    return unicode(string, sys.getfilesystemencoding() or 'utf-8').strip('"') if sys.version_info < \
                                                                                 (3,) else string.strip('"')


def parse_args():
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    subparsers = parser.add_subparsers(help='commands', dest='command')

    authenticateParser = subparsers.add_parser(Authenticate.COMMAND_NAME, help=Authenticate.HELP)
    authenticateParser.add_argument(Authenticate.AUTH_KEY_ARGUMENT_NAME,
                                    type=unicode_path,
                                    help=Authenticate.AUTH_KEY_ARGUMENT_HELP)

    mountParser = subparsers.add_parser(Mount.COMMAND_NAME, help=Mount.HELP)
    mountParser.add_argument(Mount.LOCAL_PATH_ARGUMENT_NAME,
                             type=unicode_path,
                             help=Mount.LOCAL_PATH_ARGUMENT_HELP)

    mountParser.add_argument(Mount.REMOTE_PATH_ARGUMENT_NAME,
                             type=unicode_path,
                             help=Mount.REMOTE_PATH_ARGUMENT_HELP)

    unmountParser = subparsers.add_parser(Unmount.COMMAND_NAME, help=Unmount.HELP)
    unmountParser.add_argument(Unmount.LOCAL_PATH_ARGUMENT_NAME,
                               type=unicode_path,
                               help=Unmount.LOCAL_PATH_ARGUMENT_HELP)

    backupParser = subparsers.add_parser(Backup.COMMAND_NAME, help=Backup.HELP)
    backupParser.add_argument(Backup.LOCAL_PATH_ARGUMENT_NAME,
                              type=unicode_path,
                              help=Backup.LOCAL_PATH_ARGUMENT_HELP)

    backupParser.add_argument(Backup.REMOTE_PATH_ARGUMENT_NAME,
                              type=unicode_path,
                              help=Backup.REMOTE_PATH_ARGUMENT_HELP)

    removeBackupParser = subparsers.add_parser(RemoveBackup.COMMAND_NAME, help=RemoveBackup.HELP)
    removeBackupParser.add_argument(RemoveBackup.BACKUP_ID_ARGUMENT_NAME,
                                    type=unicode_path,
                                    help=RemoveBackup.BACKUP_ID_ARGUMENT_HELP)

    syncParser = subparsers.add_parser(Sync.COMMAND_NAME, help=Sync.HELP)
    syncParser.add_argument(Sync.PLACEHOLDER_PATH_ARGUMENT_NAME,
                            type=unicode_path,
                            help=Sync.PLACEHOLDER_PATH_ARGUMENT_HELP)
    syncParser.add_argument("--" + RecursiveSync.COMMAND_NAME,
                            action="store_true",
                            default=False,
                            help=RecursiveSync.HELP,
                            required=False)
    syncParser.add_argument("--" + RecursiveSync.NO_DOWNLOAD_ARGUMENT_NAME,
                            action="store_true",
                            default=False,
                            help=RecursiveSync.NO_DOWNLOAD_ARGUMENT_HELP,
                            required=False)
    syncParser.add_argument("--" + RecursiveSync.NO_WAIT_ARGUMENT_NAME,
                            action="store_true",
                            default=False,
                            help=argparse.SUPPRESS,
                            required=False)

    streamParser = subparsers.add_parser(Stream.COMMAND_NAME, help=Stream.HELP)
    streamParser.add_argument(Stream.PATH_ARGUMENT_NAME,
                              type=unicode_path,
                              help=Stream.PATH_ARGUMENT_HELP)

    streamParser.add_argument(StreamRemote.STREAM_REMOTE_ARGUMENT_NAME,
                              action='store_true',
                              help=StreamRemote.HELP)

    refreshParser = subparsers.add_parser(Refresh.COMMAND_NAME, help=Refresh.HELP)
    refreshParser.add_argument(Refresh.FOLDER_PATH_ARGUMENT_NAME,
                               type=unicode_path,
                               help=Refresh.FOLDER_PATH_ARGUMENT_HELP)

    unsyncParser = subparsers.add_parser(Unsync.COMMAND_NAME, help=Unsync.HELP)
    unsyncParser.add_argument(Unsync.PATH_ARGUMENT_NAME,
                              type=unicode_path,
                              help=Unsync.PATH_ARGUMENT_HELP)
    unsyncParser.add_argument(ForceUnsync.FORCE_UNSYNC_ARGUMENT_NAME,
                              action='store_true',
                              help=ForceUnsync.HELP)

    xlThresholdParser = subparsers.add_parser(XLThreshold.COMMAND_NAME, help=XLThreshold.HELP)
    xlThresholdParser.add_argument(XLThreshold.THRESHOLD_ARGUMENT_NAME,
                                   choices=XLThreshold.THRESHOLD_ARGUMENT_VALUES,
                                   help=XLThreshold.THRESHOLD_ARGUMENT_HELP)

    autoUnsyncThresholdParser = subparsers.add_parser(AutoUnsyncThreshold.COMMAND_NAME, help=AutoUnsyncThreshold.HELP)
    autoUnsyncThresholdParser.add_argument(AutoUnsyncThreshold.THRESHOLD_ARGUMENT_NAME,
                                   choices=AutoUnsyncThreshold.THRESHOLD_ARGUMENT_VALUES,
                                   help=AutoUnsyncThreshold.THRESHOLD_ARGUMENT_HELP)

    autoTrashThresholdParser = subparsers.add_parser(AutoTrashThreshold.COMMAND_NAME, help=AutoTrashThreshold.HELP)
    autoTrashThresholdParser.add_argument(AutoTrashThreshold.THRESHOLD_ARGUMENT_NAME,
                                           choices=AutoTrashThreshold.THRESHOLD_ARGUMENT_VALUES,
                                           help=AutoTrashThreshold.THRESHOLD_ARGUMENT_HELP)

    placeholderThresholdParser = subparsers.add_parser(PlaceholderThreshold.COMMAND_NAME, help=PlaceholderThreshold.HELP)
    placeholderThresholdParser.add_argument(PlaceholderThreshold.THRESHOLD_ARGUMENT_NAME,
                                   choices=PlaceholderThreshold.THRESHOLD_ARGUMENT_VALUES,
                                   help=PlaceholderThreshold.THRESHOLD_ARGUMENT_HELP)

    folderSyncRuleParser = subparsers.add_parser(FolderSyncRule.COMMAND_NAME,
                                                       help=FolderSyncRule.HELP)
    folderSyncRuleParser.add_argument(FolderSyncRule.LOCAL_PATH_ARGUMENT_NAME,
                                            help=FolderSyncRule.LOCAL_PATH_ARGUMENT_HELP)
    folderSyncRuleParser.add_argument(FolderSyncRule.THRESHOLD_ARGUMENT_NAME,
                                      help=FolderSyncRule.THRESHOLD_ARGUMENT_HELP)
    folderSyncRuleParser.add_argument("--" + FolderSyncRule.EXPAND_SUBFOLDERS_ARGUMENT_NAME,
                                     help=FolderSyncRule.EXPAND_SUBFOLDERS_ARGUMENT_HELP,
                                     required=False,
                                     action="store_true",
                                     default=False)

    encPassphraseParser = subparsers.add_parser(EncPassphrase.COMMAND_NAME, help=EncPassphrase.HELP)
    encPassphraseParser.add_argument(EncPassphrase.PASSPHRASE_ARGUMENT_NAME,
                                     help=EncPassphrase.PASSPHRASE_ARGUMENT_HELP)
    encPassphraseParser.add_argument(EncPassphrase.ID_ARGUMENT_NAME,
                                     help=EncPassphrase.ID_ARGUMENT_HELP)
    encPassphraseParser.add_argument("--" + EncPassphrase.INITIALIZE_ARGUMENT_NAME,
                                     help=EncPassphrase.INITIALIZE_ARGUMENT_HELP,
                                     required=False,
                                     action="store_true",
                                     default=False)

    syncStateParser = subparsers.add_parser(SyncState.COMMAND_NAME, help=SyncState.HELP)
    syncStateParser.add_argument(SyncState.PATH_ARGUMENT_NAME,
                                 type=unicode_path,
                                 help=SyncState.PATH_ARGUMENT_HELP)
    syncStateParser.add_argument(SyncState.TEXTONLY_ARGUMENT_NAME,
                                 action='store_true',
                                 help=SyncState.TEXTONLY_ARGUMENT_HELP)

    statusParser = subparsers.add_parser(Status.COMMAND_NAME, help=Status.HELP)
    statusMutuallyExclusiveGroup = statusParser.add_mutually_exclusive_group()
    statusMutuallyExclusiveGroup.add_argument(MountsStatus.MOUNTS_STATUS_ARGUMENT_NAME,
                                              action='store_true',
                                              help=MountsStatus.HELP)
    statusMutuallyExclusiveGroup.add_argument(BackupsStatus.BACKUPS_STATUS_ARGUMENT_NAME,
                                              action='store_true',
                                              help=BackupsStatus.HELP)
    statusMutuallyExclusiveGroup.add_argument(SyncRequestsStatus.SYNC_REQUESTS_STATUS_ARGUMENT_NAME,
                                              action='store_true',
                                              help=SyncRequestsStatus.HELP)
    statusMutuallyExclusiveGroup.add_argument(UploadsStatus.UPLOADS_STATUS_ARGUMENT_NAME,
                                              action='store_true',
                                              help=UploadsStatus.HELP)
    statusMutuallyExclusiveGroup.add_argument(DownloadsStatus.DOWNLOADS_STATUS_ARGUMENT_NAME,
                                              action='store_true',
                                              help=DownloadsStatus.HELP)
    statusMutuallyExclusiveGroup.add_argument(BackgroundStatus.BACKGROUND_STATUS_ARGUMENT_NAME,
                                              action='store_true',
                                              help=BackgroundStatus.HELP)
    statusMutuallyExclusiveGroup.add_argument(TrashStatus.TRASH_STATUS_ARGUMENT_NAME,
                                              action='store_true',
                                              help=TrashStatus.HELP)
    statusMutuallyExclusiveGroup.add_argument(WaitingStatus.WAITING_STATUS_ARGUMENT_NAME,
                                              action='store_true',
                                              help=WaitingStatus.HELP)
    statusMutuallyExclusiveGroup.add_argument(NotAllowedStatus.NOT_ALLOWED_STATUS_ARGUMENT_NAME,
                                              action='store_true',
                                              help=NotAllowedStatus.HELP)
    subparsers.add_parser(Deauthorize.COMMAND_NAME, help=Deauthorize.HELP)
    subparsers.add_parser(Diagnostics.COMMAND_NAME, help=Diagnostics.HELP)
    subparsers.add_parser(BackupNow.COMMAND_NAME, help=BackupNow.HELP)
    subparsers.add_parser(EmptyTrash.COMMAND_NAME, help=EmptyTrash.HELP)
    subparsers.add_parser(RestoreTrash.COMMAND_NAME, help=RestoreTrash.HELP)
    subparsers.add_parser(Shutdown.COMMAND_NAME, help=Shutdown.HELP)

    if not sys.argv[1:]:
        parser.print_usage()
        return None
    return parser.parse_args()


def get_protocol_server_port(registryPath):
    try:
        with open(registryPath, 'r') as f:
            data = json.loads(f.read())
            return data["current"][PROTOCOL_SERVER_PORT_KEY]
    except Exception as e:
        return None


def expand_user(path):
    if IS_WINDOWS:
        if path.startswith(u'~'):
            get_folder_path = getattr(windll.shell32, 'SHGetKnownFolderPath', None)
            if get_folder_path is not None:
                ptr = c_wchar_p()
                get_folder_path(byref(FOLDERID_Profile), 0, 0, byref(ptr))
                return ptr.value + path[1:]
            else:
                get_folder_path = getattr(windll.shell32, 'SHGetSpecialFolderPathW', None)
                buf = create_unicode_buffer(300)
                get_folder_path(None, buf, CSIDL_PROFILE, False)
                return buf.value + path[1:]
        return path
    else:
        return os.path.expanduser(path)

def output_message(message, stderr=False, color=None):
    if not message:
        return
    if IS_WINDOWS:
        if (stderr and sys.stderr.isatty()) or ((not stderr) and sys.stdout.isatty()):
            # if we are writing to the console in windows we need to use WriteConsoleW for unicode output
            handle = windll.kernel32.GetStdHandle(STD_ERR_HANDLE if stderr else STD_OUT_HANDLE)
            if handle and handle != INVALID_HANDLE:
                chars_written = c_int(0)
                if color:
                    consoleInfo = CONSOLE_SCREEN_BUFFER_INFO()
                    windll.kernel32.GetConsoleScreenBufferInfo(handle, byref(consoleInfo))
                    origionalConsoleColors = consoleInfo.wAttributes
                    origionalBackgroundColor = origionalConsoleColors & 0x0070
                    newColors = color | origionalBackgroundColor | OdriveSynchronousCommand._FG_COLOR_INTENSE
                    windll.kernel32.SetConsoleTextAttribute(handle, newColors)
                    windll.kernel32.WriteConsoleW(handle, message, len(message), byref(chars_written), None)
                    windll.kernel32.SetConsoleTextAttribute(handle, origionalConsoleColors)
                else:
                    windll.kernel32.WriteConsoleW(handle, message, len(message), byref(chars_written), None)
                return
    if stderr:
        sys.stderr.write(message)
        sys.stderr.flush()
    else:
        sys.stdout.write(message)
        sys.stdout.flush()

def get_os_encoded_path(path):
    path = make_unicode(path)
    if sys.platform.startswith('win32'):
        path = u'\\\\?\\' + path
    else:
        path = path.encode('utf-8')
    return path

def make_unicode(path):
    if not isinstance(path, unicode):
        path = unicode(path, 'utf-8')
    else:
        path = unicode(path.encode('utf-8'), 'utf-8')
    return path

def main():
    args = parse_args()

    if not args:
        print(NO_ARGS)
        sys.exit(1)

    AGENT_PORT_REGISTRY_FILE_PATH = os.path.join(expand_user('~'), '.odrive-agent', '.oreg')
    DESKTOP_PORT_REGISTRY_FILE_PATH = os.path.join(expand_user('~'), '.odrive', '.oreg')

    agentProtocolServerPort = get_protocol_server_port(AGENT_PORT_REGISTRY_FILE_PATH)
    desktopProtocolServerPort = get_protocol_server_port(DESKTOP_PORT_REGISTRY_FILE_PATH)

    if not (agentProtocolServerPort or desktopProtocolServerPort):
        print(REQUIRES_ODRIVE)
        sys.exit(1)

    if args.command == Authenticate.COMMAND_NAME:
        command = Authenticate(agentPort=agentProtocolServerPort,
                               desktopPort=desktopProtocolServerPort,
                               authKey=getattr(args, Authenticate.AUTH_KEY_ARGUMENT_NAME))
    elif args.command == Deauthorize.COMMAND_NAME:
        command = Deauthorize(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
    elif args.command == Diagnostics.COMMAND_NAME:
        command = Diagnostics(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
    elif args.command == BackupNow.COMMAND_NAME:
        command = BackupNow(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
    elif args.command == Mount.COMMAND_NAME:
        command = Mount(agentPort=agentProtocolServerPort,
                        desktopPort=desktopProtocolServerPort,
                        localPath=os.path.abspath(expand_user(getattr(args, Mount.LOCAL_PATH_ARGUMENT_NAME))),
                        remotePath=getattr(args, Mount.REMOTE_PATH_ARGUMENT_NAME))
    elif args.command == Unmount.COMMAND_NAME:
        command = Unmount(agentPort=agentProtocolServerPort,
                          desktopPort=desktopProtocolServerPort,
                          localPath=os.path.abspath(expand_user(getattr(args, Unmount.LOCAL_PATH_ARGUMENT_NAME))))
    elif args.command == Backup.COMMAND_NAME:
        command = Backup(agentPort=agentProtocolServerPort,
                         desktopPort=desktopProtocolServerPort,
                         localPath=os.path.abspath(expand_user(getattr(args, Backup.LOCAL_PATH_ARGUMENT_NAME))),
                         remotePath=getattr(args, Backup.REMOTE_PATH_ARGUMENT_NAME))
    elif args.command == RemoveBackup.COMMAND_NAME:
        command = RemoveBackup(agentPort=agentProtocolServerPort,
                               desktopPort=desktopProtocolServerPort,
                               backupId=getattr(args, RemoveBackup.BACKUP_ID_ARGUMENT_NAME))
    elif args.command == Sync.COMMAND_NAME:
        syncPath = os.path.abspath(expand_user(getattr(args, Sync.PLACEHOLDER_PATH_ARGUMENT_NAME)))
        if getattr(args, RecursiveSync.COMMAND_NAME):
            command = RecursiveSync(agentPort=agentProtocolServerPort,
                                    desktopPort=desktopProtocolServerPort,
                                    folderPath=syncPath,
                                    noDownload=getattr(args, RecursiveSync.NO_DOWNLOAD_ARGUMENT_NAME),
                                    noWait=getattr(args, RecursiveSync.NO_WAIT_ARGUMENT_NAME))
        else:
            command = Sync(agentPort=agentProtocolServerPort,
                           desktopPort=desktopProtocolServerPort,
                           placeholderPath=syncPath)
    elif args.command == Stream.COMMAND_NAME:
        if args.remote:
            command = StreamRemote(agentPort=agentProtocolServerPort,
                                   desktopPort=desktopProtocolServerPort,
                                   path=getattr(args, StreamRemote.PATH_ARGUMENT_NAME))
        else:
            command = Stream(agentPort=agentProtocolServerPort,
                             desktopPort=desktopProtocolServerPort,
                             path=os.path.abspath(expand_user(getattr(args, Stream.PATH_ARGUMENT_NAME))))
    elif args.command == Refresh.COMMAND_NAME:
        command = Refresh(agentPort=agentProtocolServerPort,
                          desktopPort=desktopProtocolServerPort,
                          folderPath=os.path.abspath(expand_user(getattr(args, Refresh.FOLDER_PATH_ARGUMENT_NAME))))
    elif args.command == Status.COMMAND_NAME:
        if args.mounts:
            command = MountsStatus(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
        elif args.backups:
            command = BackupsStatus(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
        elif args.sync_requests:
            command = SyncRequestsStatus(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
        elif args.uploads:
            command = UploadsStatus(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
        elif args.downloads:
            command = DownloadsStatus(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
        elif args.background:
            command = BackgroundStatus(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
        elif args.trash:
            command = TrashStatus(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
        elif args.waiting:
            command = WaitingStatus(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
        elif args.not_allowed:
            command = NotAllowedStatus(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
        else:
            command = Status(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
    elif args.command == SyncState.COMMAND_NAME:
        command = SyncState(agentPort=agentProtocolServerPort,
                            desktopPort=desktopProtocolServerPort,
                            path=os.path.abspath(expand_user(getattr(args, SyncState.PATH_ARGUMENT_NAME))),
                            textonly=args.textonly)
    elif args.command == Unsync.COMMAND_NAME:
        if args.force:
            command = ForceUnsync(agentPort=agentProtocolServerPort,
                                  desktopPort=desktopProtocolServerPort,
                                  path=os.path.abspath(expand_user(getattr(args, ForceUnsync.PATH_ARGUMENT_NAME))))
        else:
            command = Unsync(agentPort=agentProtocolServerPort,
                             desktopPort=desktopProtocolServerPort,
                             path=os.path.abspath(expand_user(getattr(args, Unsync.PATH_ARGUMENT_NAME))))
    elif args.command == XLThreshold.COMMAND_NAME:
        command = XLThreshold(agentPort=agentProtocolServerPort,
                              desktopPort=desktopProtocolServerPort,
                              threshold=getattr(args, XLThreshold.THRESHOLD_ARGUMENT_NAME))
    elif args.command == AutoUnsyncThreshold.COMMAND_NAME:
        command = AutoUnsyncThreshold(agentPort=agentProtocolServerPort,
                              desktopPort=desktopProtocolServerPort,
                              threshold=getattr(args, AutoUnsyncThreshold.THRESHOLD_ARGUMENT_NAME))
    elif args.command == AutoTrashThreshold.COMMAND_NAME:
        command = AutoTrashThreshold(agentPort=agentProtocolServerPort,
                              desktopPort=desktopProtocolServerPort,
                              threshold=getattr(args, AutoTrashThreshold.THRESHOLD_ARGUMENT_NAME))
    elif args.command == PlaceholderThreshold.COMMAND_NAME:
        command = PlaceholderThreshold(agentPort=agentProtocolServerPort,
                              desktopPort=desktopProtocolServerPort,
                              threshold=getattr(args, PlaceholderThreshold.THRESHOLD_ARGUMENT_NAME))
    elif args.command == FolderSyncRule.COMMAND_NAME:
        command = FolderSyncRule(agentPort=agentProtocolServerPort,
                              desktopPort=desktopProtocolServerPort,
                              path=getattr(args, FolderSyncRule.LOCAL_PATH_ARGUMENT_NAME),
                              threshold=getattr(args, FolderSyncRule.THRESHOLD_ARGUMENT_NAME),
                              expandSubfolders=getattr(args, FolderSyncRule.EXPAND_SUBFOLDERS_ARGUMENT_NAME))
    elif args.command == EncPassphrase.COMMAND_NAME:
        command = EncPassphrase(agentPort=agentProtocolServerPort,
                                desktopPort=desktopProtocolServerPort,
                                passphrase=getattr(args, EncPassphrase.PASSPHRASE_ARGUMENT_NAME),
                                id=getattr(args, EncPassphrase.ID_ARGUMENT_NAME),
                                initialize=getattr(args, EncPassphrase.INITIALIZE_ARGUMENT_NAME))
    elif args.command == EmptyTrash.COMMAND_NAME:
        command = EmptyTrash(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
    elif args.command == RestoreTrash.COMMAND_NAME:
        command = RestoreTrash(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
    elif args.command == Shutdown.COMMAND_NAME:
        command = Shutdown(agentPort=agentProtocolServerPort, desktopPort=desktopProtocolServerPort)
    else:
        print(INVALID_OPTION)
        sys.exit(1)

    success = command.execute()

    if success:
        sys.exit(0)
    else:
        print(ERROR_SENDING_COMMAND)
        sys.exit(1)


if __name__ == "__main__":
    main()
