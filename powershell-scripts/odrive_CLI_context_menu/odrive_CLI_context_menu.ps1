$syncpath=$args[0]
$global:o="$HOME\.odrive\common"
$global:syncbin="$o\odrive.exe"
[void] [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms")
[void] [System.Reflection.Assembly]::LoadWithPartialName("System.Drawing")

function do_sync {
    param( [string]$syncpath )

    $Form = New-Object System.Windows.Forms.Form
    $Form.width = 500
    $Form.height = 250
    $Form.Text = "odrive Sync"
    $Form.StartPosition = "CenterScreen"
    
    $RecCheck = new-object System.Windows.Forms.checkbox
	$RecCheck.Location = new-object System.Drawing.Size(30,10)
	$RecCheck.Size = new-object System.Drawing.Size(200,20)
	$RecCheck.Text = "Recursive (for folder sync)"
	$RecCheck.Checked = $false
    $recurse = @{recurse = $false}
  	$Form.Controls.Add($RecCheck)

    $DLCheck = new-object System.Windows.Forms.checkbox
	$DLCheck.Location = new-object System.Drawing.Size(30,30)
	$DLCheck.Size = new-object System.Drawing.Size(200,20)
	$DLCheck.Text = "Download All (for folder sync)"
	$DLCheck.Checked = $false
	$Form.Controls.Add($DLCheck)

    $OutputBox = New-Object System.Windows.Forms.RichTextBox
    $OutputBox.Location = new-object System.Drawing.Size(30,50)
	$OutputBox.Size = new-object System.Drawing.Size(430,100)
    $form.Controls.Add($OutputBox)

    $SyncButton = new-object System.Windows.Forms.Button
    $SyncButton.Location = new-object System.Drawing.Size(30,160)
    $SyncButton.Size = new-object System.Drawing.Size(100,40)
    $SyncButton.Text = "Sync"
    $SyncButton.Add_Click({
        if ([string]::IsNullOrEmpty($syncpath))  {
            $OutputBox.text = "Need a Path!"
            return
        }
        $OutputBox.text = "Syncing ..."
        if ((Get-Item $syncpath) -is [system.io.fileinfo]) {
            $SyncOutput = & "$syncbin" "sync" "$syncpath" 2>&1
            $syncpath = $syncpath.Substring(0, $syncpath.LastIndexOf('.'))
        }
        $OutputBox.appendtext("`n$SyncOutput`n")
        if($RecCheck.Checked) {
            $recurse = @{recurse = $true}
            $OutputBox.appendtext("`n`nExpanding all folders in $syncpath ...`n")
            while ((Get-ChildItem $syncpath -Filter "*.cloudf" @recurse | Measure-Object).Count) {
                Get-ChildItem -File -Path "$syncpath" -Filter "*.cloudf" @recurse | % {$SyncOutput = & "$syncbin" "sync" "$($_.FullName)" 2>&1;$OutputBox.appendtext("Expanded: $SyncOutput`n");$OutputBox.SelectionStart = $SyncOutput.TextLength;$OutputBox.ScrollToCaret();$OutputBox.Focus()}
            }
        }
        if($DLCheck.Checked) {
            if($RecCheck.Checked){$OutputBox.appendtext("`n`nSyncing all files in $syncpath recursively ...`n")}
			while ((Get-ChildItem $syncpath -Filter "*.cloud" @Recurse | Measure-Object).Count) {
                Get-ChildItem -File -Path "$syncpath" -Filter "*.cloud" @recurse | % {$SyncOutput = & "$syncbin" "sync" "$($_.FullName)" 2>&1;$OutputBox.appendtext("Synced: $SyncOutput`n");$OutputBox.SelectionStart = $OutputBox.TextLength;$OutputBox.ScrollToCaret();$OutputBox.Focus()}
            }
        }
        $OutputBox.appendtext("`nDone!")
    })
    $form.Controls.Add($SyncButton)
    $Form.Add_Shown({$Form.Activate()})
    [void] $Form.ShowDialog()
}
if(!(Test-Path -Path $syncbin)) {
    echo "Downloading CLI binary ... "
    (New-Object System.Net.WebClient).DownloadFile("https://dl.odrive.com/odrivecli-win", "$o\oc.zip")
    $shl=new-object -com shell.application
    $shl.namespace("$o").copyhere($shl.namespace("$o\oc.zip").items(),0x10)
    del "$o\oc.zip";
    echo "Done!"
}
do_sync -syncpath $syncpath