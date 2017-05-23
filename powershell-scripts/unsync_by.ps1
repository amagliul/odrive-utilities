Param(
   [parameter()][alias("e")][string]$EXTENSION,
   [parameter()][alias("s")][string]$SIZE,
   [parameter()][alias("d")][string]$DAYS,
   [parameter()][alias("p")][string]$DIRPATH,
   [parameter()][alias("r")][switch]$RECURSIVE,
   [parameter()][alias("h")][switch]$HELP
)
$O="$HOME\.odrive\common"
$UNSYNC_BIN="$o\odrive.exe"

if ($RECURSIVE) {
   $PARAM = @{Recurse = $true}
}
else {
   $PARAM = @{Recurse = $false}
}

if ($HELP) {
   echo "Usage: unsync_by [-e <extension>] [-s <size in kilobytes>] [-d <days>] [-p <directory path>] [-r]"
   echo "Help: Unsync files by extension, size, or days old for a given directory"
   echo "Options:"
   echo "-e -extension Unsyncs files with the specified extension"
   echo "-s -size Unsyncs files larger than the specified size in kilobytes"
   echo "-d -days Unsyncs files older than the specified day"
   echo "-p -dirpath The specified path"
   echo "-r -recursive Unsyncs files recursively through the specified path"
   echo "-h -help Help"
   break
}
if(!(Test-Path -Path $UNSYNC_BIN)) {
    echo "Downloading CLI binary ... "
    (New-Object System.Net.WebClient).DownloadFile("https://dl.odrive.com/odrivecli-win", "$O\oc.zip")
    $shl=new-object -com shell.application
    $shl.namespace("$O").copyhere($shl.namespace("$O\oc.zip").items(),0x10)
    del "$O\oc.zip"
    echo "Done!"
}
if (-Not ($DIRPATH)){
   echo "Invalid arguments. Please consult help for usage details (-h, -help)." 
   break
}
elseif ($EXTENSION) {
   echo "unsyncing all files of $EXTENSION type in $DIRPATH"
   Get-ChildItem -File -Path "$DIRPATH\*" -Filter "*.$EXTENSION" @PARAM | % {& "$UNSYNC_BIN" unsync "$($_.FullName)"}
}
elseif ($SIZE) {
   echo "unsyncing all files larger than $SIZE kilobytes in $DIRPATH"
   Get-ChildItem -File -Path "$DIRPATH\*" -Exclude *.cloud* @PARAM | Where-Object {$($_.Length) -gt "$($SIZE)KB"} | % {& "$UNSYNC_BIN" unsync "$($_.FullName)"}
}
elseif ($DAYS) {
   echo "unsyncing all files older than $DAYS days in $DIRPATH"
   $SUBDATE = $((Get-Date).AddDays(-$($DAYS)))
   echo $SUBDATE
   Get-ChildItem -File -Path "$DIRPATH\*" -Exclude *.cloud* @PARAM | Where-Object {$($_.LastWriteTime) -lt $SUBDATE} | % {& "$UNSYNC_BIN" unsync "$($_.FullName)"}
}
else {
   echo "Invalid arguments. Please consult help for usage details (-h, -help)."
}