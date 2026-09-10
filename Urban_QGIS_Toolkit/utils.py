import os
import subprocess
import threading
from qgis.PyQt.QtWidgets import QMessageBox

def run_installer_background(qgis_path, qgis_version, commands, startupinfo):
    try:
        proc = subprocess.Popen(
            f'cmd /c "{commands}"',
            shell=True,
            cwd=qgis_path,
            startupinfo=startupinfo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = proc.communicate()

        if proc.returncode == 0:
            print(f"\n[OK] QGIS {qgis_version} 환경 패키지 설치 완료! 이제 기능을 즉시 사용할 수 있습니다.")
        else:
            print(f"\n[ERROR] QGIS {qgis_version} 환경 설치 실패 (코드: {proc.returncode})")
            if stderr:
                print(f"[ERROR] 에러 내용: {stderr.decode('cp949', errors='ignore')}")

    except Exception as e:
        print(f"\n[ERROR] 백그라운드 감시 중 예외 발생: {e}")


def check_playwright_installed(iface):
    try:
        import sys
        if 'playwright' in sys.modules:
            del sys.modules['playwright']

        import playwright
        return True
    except ImportError:
        print("[WARN] 필수 패키지가 없습니다. 설치 안내창을 가동합니다.")

        current_dir = os.path.dirname(os.path.abspath(__file__))
        bat_filename = "install_playwright.bat"
        bat_path = os.path.join(current_dir, bat_filename)
        base_dir = r"C:\Program Files"

        if not os.path.exists(bat_path):
            QMessageBox.critical(iface.mainWindow(), "오류", f"{bat_filename} 파일을 찾을 수 없습니다.\n경로: {bat_path}")
            return False

        reply = QMessageBox.information(
            iface.mainWindow(),
            "필수 패키지 설치 안내",
            "이 기능을 사용하려면 필수 패키지(Playwright)가 필요합니다.\n"
            "(chrome 브라우저 제어를 위한 라이브러리 입니다.)\n\n"
            "백그라운드 자동 설치를 진행하시겠습니까?",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok
        )

        if reply == QMessageBox.Cancel:
            print("사용자가 패키지 설치를 취소했습니다.")
            return False

        installed_any = False
        if os.path.exists(base_dir):
            for folder_name in os.listdir(base_dir):
                if "QGIS" in folder_name:
                    qgis_path = os.path.join(base_dir, folder_name)
                    osgeo4w_bat = os.path.join(qgis_path, "OSGeo4W.bat")

                    if os.path.exists(osgeo4w_bat):
                        installed_any = True
                        qgis_version = folder_name.replace("QGIS", "").strip()
                        if not qgis_version:
                            qgis_version = folder_name

                        print(f"QGIS {qgis_version} 환경 백그라운드 설치 시작...")

                        commands = f'"{osgeo4w_bat}" call "{bat_path}"'

                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        startupinfo.wShowWindow = subprocess.SW_HIDE

                        t = threading.Thread(
                            target=run_installer_background,
                            args=(qgis_path, qgis_version, commands, startupinfo),
                            daemon=True
                        )
                        t.start()

        if installed_any:
            QMessageBox.information(
                iface.mainWindow(),
                "설치 시작",
                "백그라운드에서 설치가 시작되었습니다.\n\n"
                "대략 30초~1분 뒤에 검색/로그인 버튼을 다시 클릭하시면 기능이 정상 작동합니다!"
            )
        else:
            print("[WARN] 유효한 QGIS 설치 환경을 찾지 못했습니다.")

        return False
