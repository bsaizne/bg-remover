"""明暗主题 QSS。"""
from __future__ import annotations

DARK = """
QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #1e1e1e;
}
QTabWidget::pane {
    border: 1px solid #333;
    background-color: #252526;
}
QTabBar::tab {
    background: #2d2d30;
    color: #ccc;
    padding: 6px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #007acc;
    color: white;
}
QListWidget, QTreeWidget, QTableView, QTextEdit, QPlainTextEdit {
    background-color: #1b1b1b;
    border: 1px solid #3f3f3f;
    border-radius: 4px;
}
QPushButton {
    background-color: #3a3d41;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 5px 14px;
}
QPushButton:hover { background-color: #4a4d51; }
QPushButton:pressed { background-color: #2d2d30; }
QPushButton:disabled { color: #777; background-color: #2d2d30; }
QPushButton#primary {
    background-color: #007acc;
    border: 1px solid #007acc;
    color: white;
}
QPushButton#primary:hover { background-color: #1a8ad1; }
QPushButton#danger {
    background-color: #c42b1c;
    border: 1px solid #c42b1c;
    color: white;
}
QPushButton#danger:hover { background-color: #d23c2c; }
QComboBox, QSpinBox, QLineEdit {
    background-color: #2d2d30;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 4px 8px;
}
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background-color: #2d2d30;
    selection-background-color: #007acc;
}
QCheckBox { spacing: 6px; }
QProgressBar {
    border: 1px solid #555;
    border-radius: 4px;
    background-color: #2d2d30;
    text-align: center;
    color: #e0e0e0;
}
QProgressBar::chunk { background-color: #007acc; border-radius: 3px; }
QStatusBar { background-color: #2d2d30; color: #aaa; }
QSplitter::handle { background-color: #3f3f3f; }
QScrollBar:vertical { background: #2d2d30; width: 10px; }
QScrollBar::handle:vertical { background: #555; border-radius: 5px; min-height: 20px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QGraphicsView { background-color: #1b1b1b; border: 1px solid #3f3f3f; }
QToolTip {
    background-color: #2d2d30;
    color: #e0e0e0;
    border: 1px solid #555;
}
"""

LIGHT = """
QWidget {
    background-color: #f5f5f5;
    color: #1e1e1e;
    font-size: 13px;
}
QMainWindow, QDialog { background-color: #f5f5f5; }
QTabWidget::pane { border: 1px solid #ddd; background-color: #ffffff; }
QTabBar::tab { background: #e8e8e8; color: #555; padding: 6px 16px; margin-right: 2px; }
QTabBar::tab:selected { background: #007acc; color: white; }
QListWidget, QTreeWidget, QTableView, QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    border: 1px solid #ddd;
    border-radius: 4px;
}
QPushButton {
    background-color: #e8e8e8;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 5px 14px;
}
QPushButton:hover { background-color: #f0f0f0; }
QPushButton:pressed { background-color: #ddd; }
QPushButton:disabled { color: #999; background-color: #eee; }
QPushButton#primary { background-color: #007acc; border: 1px solid #007acc; color: white; }
QPushButton#primary:hover { background-color: #1a8ad1; }
QPushButton#danger { background-color: #c42b1c; border: 1px solid #c42b1c; color: white; }
QPushButton#danger:hover { background-color: #d23c2c; }
QComboBox, QSpinBox, QLineEdit {
    background-color: #ffffff;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 4px 8px;
}
QComboBox::drop-down { border: none; width: 22px; }
QProgressBar {
    border: 1px solid #ccc;
    border-radius: 4px;
    background-color: #fff;
    text-align: center;
}
QProgressBar::chunk { background-color: #007acc; border-radius: 3px; }
QStatusBar { background-color: #e8e8e8; color: #666; }
QSplitter::handle { background-color: #ddd; }
QGraphicsView { background-color: #fff; border: 1px solid #ddd; }
QToolTip { background-color: #fff; color: #1e1e1e; border: 1px solid #ccc; }
"""

THEMES = {"dark": DARK, "light": LIGHT}
