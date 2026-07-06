from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
        from app.ui.main_window import MainWindow
        from app.ui.style import apply_app_theme
    except ImportError as exc:
        print("PySide6 is required to start the GUI.")
        print("Install dependencies with: python -m pip install -r requirements.txt")
        print(f"Import error: {exc}")
        return 1

    app = QApplication(sys.argv)
    apply_app_theme(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

