
import sys
import os
import cProfile
import pstats
import io
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from src.bootstrap import create_application
from src.ui.window.window import MainWindow

def run():
    app = create_application()
    window = MainWindow()
    window.show()
    
    # Profile for 10 seconds of idle
    pr = cProfile.Profile()
    pr.enable()
    
    def finish_profile():
        pr.disable()
        s = io.StringIO()
        sortby = 'cumulative'
        ps = pstats.Stats(pr, stream=s).sort_stats(sortby)
        ps.print_stats(50)
        with open("idle_profile.txt", "w") as f:
            f.write(s.getvalue())
        QApplication.instance().quit()

    QTimer.singleShot(10000, finish_profile)
    app.exec()

if __name__ == "__main__":
    run()
