"""Self-contained Korean HTML design reviews for stations 3/4."""
from datetime import datetime,timezone,timedelta
import html
import json


def report_html(r):
    from review_layout import compact_report
    return compact_report(r['index'],r)
