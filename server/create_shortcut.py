import os
import sys
import subprocess

def create_desktop_shortcut():
    try:
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        shortcut_path = os.path.join(desktop, "AideLink.lnk")
        
        # 动态获取当前的 pythonw.exe 和 start_manager.py 路径，杜绝硬编码
        python_exe = sys.executable
        pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
        if not os.path.exists(pythonw_exe):
            pythonw_exe = python_exe
            
        curr_dir = os.path.dirname(os.path.abspath(__file__))
        start_script = os.path.join(curr_dir, "start_manager.py")
        
        # 转义单引号以防止 powershell 崩溃
        shortcut_path_esc = shortcut_path.replace("'", "''")
        pythonw_exe_esc = pythonw_exe.replace("'", "''")
        start_script_esc = start_script.replace("'", "''")
        curr_dir_esc = curr_dir.replace("'", "''")
        
        powershell_cmd = f"""
        $WshShell = New-Object -ComObject WScript.Shell
        $Shortcut = $WshShell.CreateShortcut('{shortcut_path_esc}')
        $Shortcut.TargetPath = '{pythonw_exe_esc}'
        $Shortcut.Arguments = '"{start_script_esc}"'
        $Shortcut.Description = '一键启动 AideLink 桌面控制台与后台桥接服务'
        $Shortcut.WorkingDirectory = '{curr_dir_esc}'
        $Shortcut.IconLocation = 'shell32.dll,238'
        $Shortcut.Save()
        """
        
        res = subprocess.run(["powershell", "-Command", powershell_cmd], capture_output=True, text=True)
        if res.returncode == 0:
            print(f"[OK] Created Desktop shortcut at: {shortcut_path}")
            return True
        else:
            print(f"[FAIL] PowerShell failed: {res.stderr}")
            return False
    except Exception as e:
        print(f"[FAIL] Failed to create Desktop shortcut: {e}")
        return False

if __name__ == "__main__":
    create_desktop_shortcut()