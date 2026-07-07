"""
アプリ全体の日時規約（2026-07-03変更）。

「今日」の判定・記録時刻はすべて日本時間（JST, UTC+9）基準とする。
日本はサマータイムがないため固定オフセットで安全。
DBにはnaive datetime（JSTの値）をそのまま保存する。

従来のutcnow基準では日本時間の深夜0時〜朝9時の間「今日」が前日に
ずれる問題があったため変更した。datetime.utcnow()を直接使わず、
必ずこのモジュールの now_app() / today_app() を使うこと。
"""
from datetime import date, datetime, timedelta

JST_OFFSET = timedelta(hours=9)


def now_app() -> datetime:
    """アプリ全体の現在時刻（JST・naive）。"""
    return datetime.utcnow() + JST_OFFSET


def today_app() -> date:
    """アプリ全体の「今日」（JST基準）。"""
    return now_app().date()
