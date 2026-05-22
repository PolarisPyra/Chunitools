
import sys
import os
import time
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

# Add src to path
sys.path.append(os.path.join(os.getcwd(), "src"))

from src.bootstrap import create_application
from src.ui.window.window import MainWindow

def profile_sequence(window):
    print("Automation: Loading chart...")
    chart_path = os.path.abspath("charts/2967_04.c2s")
    window.load_chart_file(chart_path)
    
    # Wait for loading to settle
    print("Automation: Waiting for chart to settle...")
    
    def start_playback():
        print("Automation: Starting playback...")
        window.toggle_playback()
        
        # After 10 seconds of playback, quit
        print("Automation: Playing for 10 seconds...")
        QTimer.singleShot(10000, QApplication.instance().quit)

    QTimer.singleShot(2000, start_playback)

def run():
    # Use the venv's python and settings
    app = create_application()
    window = MainWindow()
    window.show()
    
    # Start the sequence after window is shown
    QTimer.singleShot(1000, lambda: profile_sequence(window))
    
    print("Automation: Application starting...")
    ret = app.exec()
    print("Automation: Application closed.")
    sys.exit(ret)

if __name__ == "__main__":
    run()
