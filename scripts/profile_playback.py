
import sys
import os
import cProfile
import pstats
import io
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from src.app.bootstrap import create_application
from src.ui.window.window import MainWindow

def run():
    app = create_application()
    window = MainWindow()
    window.show()
    
    # Automation: Loading chart
    chart_path = os.path.abspath("charts/2967_04.c2s")
    window.load_chart_file(chart_path)
    
    def start_playback_and_profile():
        window.toggle_playback()
        
        pr = cProfile.Profile()
        pr.enable()
        
        def finish_profile():
            pr.disable()
            s = io.StringIO()
            sortby = 'cumulative'
            ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
            ps.print_stats(100)
            with open("playback_profile.txt", "w") as f:
                f.write(s.getvalue())
            QApplication.instance().quit()

        QTimer.singleShot(5000, finish_profile)

    QTimer.singleShot(2000, start_playback_and_profile)
    app.exec()

if __name__ == "__main__":
    run()
