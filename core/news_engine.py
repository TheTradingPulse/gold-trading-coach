import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "analysis"))
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, timedelta
import json


# High-impact economic events schedule for 2026
# In production, this would come from an API like Trading Economics or Financial Modeling Prep
# For V1, we hardcode major recurring events

HIGH_IMPACT_EVENTS = [
    # FOMC Meetings (2026 schedule - approximate dates)
    {"date": "2026-01-28", "event": "FOMC Meeting", "impact": "HIGH", "time": "14:00 ET"},
    {"date": "2026-03-18", "event": "FOMC Meeting", "impact": "HIGH", "time": "14:00 ET"},
    {"date": "2026-05-06", "event": "FOMC Meeting", "impact": "HIGH", "time": "14:00 ET"},
    {"date": "2026-06-17", "event": "FOMC Meeting", "impact": "HIGH", "time": "14:00 ET"},
    {"date": "2026-07-29", "event": "FOMC Meeting", "impact": "HIGH", "time": "14:00 ET"},
    {"date": "2026-09-23", "event": "FOMC Meeting", "impact": "HIGH", "time": "14:00 ET"},
    {"date": "2026-11-05", "event": "FOMC Meeting", "impact": "HIGH", "time": "14:00 ET"},
    {"date": "2026-12-16", "event": "FOMC Meeting", "impact": "HIGH", "time": "14:00 ET"},
    
    # Regular monthly events (first week of each month typically)
    {"date": "2026-07-02", "event": "NFP (Non-Farm Payrolls)", "impact": "HIGH", "time": "08:30 ET"},
    {"date": "2026-07-08", "event": "CPI (Consumer Price Index)", "impact": "HIGH", "time": "08:30 ET"},
    {"date": "2026-07-15", "event": "PPI (Producer Price Index)", "impact": "MEDIUM", "time": "08:30 ET"},
    {"date": "2026-07-17", "event": "Jobless Claims", "impact": "MEDIUM", "time": "08:30 ET"},
    {"date": "2026-07-29", "event": "GDP (Q2 Advance)", "impact": "HIGH", "time": "08:30 ET"},
    
    {"date": "2026-08-07", "event": "NFP (Non-Farm Payrolls)", "impact": "HIGH", "time": "08:30 ET"},
    {"date": "2026-08-12", "event": "CPI (Consumer Price Index)", "impact": "HIGH", "time": "08:30 ET"},
    {"date": "2026-08-13", "event": "PPI (Producer Price Index)", "impact": "MEDIUM", "time": "08:30 ET"},
    
    {"date": "2026-09-04", "event": "NFP (Non-Farm Payrolls)", "impact": "HIGH", "time": "08:30 ET"},
    {"date": "2026-09-09", "event": "CPI (Consumer Price Index)", "impact": "HIGH", "time": "08:30 ET"},
    
    {"date": "2026-10-02", "event": "NFP (Non-Farm Payrolls)", "impact": "HIGH", "time": "08:30 ET"},
    {"date": "2026-10-13", "event": "CPI (Consumer Price Index)", "impact": "HIGH", "time": "08:30 ET"},
    
    {"date": "2026-11-06", "event": "NFP (Non-Farm Payrolls)", "impact": "HIGH", "time": "08:30 ET"},
    {"date": "2026-11-10", "event": "CPI (Consumer Price Index)", "impact": "HIGH", "time": "08:30 ET"},
    
    {"date": "2026-12-04", "event": "NFP (Non-Farm Payrolls)", "impact": "HIGH", "time": "08:30 ET"},
    {"date": "2026-12-10", "event": "CPI (Consumer Price Index)", "impact": "HIGH", "time": "08:30 ET"},
]


def check_upcoming_events():
    """Check for high-impact events in the next 48 hours"""
    now = datetime.now()
    upcoming = []
    active = []
    
    for event in HIGH_IMPACT_EVENTS:
        event_date = datetime.strptime(event["date"], "%Y-%m-%d")
        event_datetime = datetime.combine(
            event_date,
            datetime.strptime(event["time"].replace(" ET", ""), "%H:%M").time()
        )
        
        # Events happening now (within 2 hours)
        time_diff = event_datetime - now
        hours_until = time_diff.total_seconds() / 3600
        
        if 0 <= hours_until <= 2:
            active.append({
                **event,
                "status": "ACTIVE",
                "minutes_until": int(hours_until * 60)
            })
        
        # Events in next 48 hours
        if 0 <= hours_until <= 48:
            upcoming.append({
                **event,
                "hours_until": round(hours_until, 1)
            })
    
    return active, upcoming


def get_confidence_adjustment():
    """Calculate confidence adjustment based on upcoming events"""
    active, upcoming = check_upcoming_events()
    
    if active:
        return -30  # Major event active - reduce confidence significantly
    
    high_impact_near = [e for e in upcoming if e["impact"] == "HIGH" and e["hours_until"] <= 12]
    
    if high_impact_near:
        return -20  # High impact event within 12 hours
    
    if upcoming and upcoming[0]["hours_until"] <= 24:
        return -10  # Events within 24 hours
    
    return 0  # No adjustment needed


def generate_news_warning():
    """Generate a warning message about upcoming news events"""
    active, upcoming = check_upcoming_events()
    
    if active:
        warnings = []
        for event in active:
            mins = event["minutes_until"]
            if mins <= 0:
                warnings.append(f"🚨 *ACTIVE NOW:* {event['event']} ({event['impact']} impact)")
            else:
                warnings.append(f"⚠️ *IN {mins} MINUTES:* {event['event']} ({event['impact']} impact)")
        
        message = "\n".join(warnings)
        message += "\n\n*Recommendation:* Reduce position size or wait until after the event."
        return message, "HIGH"
    
    if upcoming:
        near_high = [e for e in upcoming if e["impact"] == "HIGH" and e["hours_until"] <= 12]
        if near_high:
            message = f"⚠️ *HIGH IMPACT EVENT:* {near_high[0]['event']} in {near_high[0]['hours_until']} hours ({near_high[0]['time']})"
            message += "\n\n*Recommendation:* Be cautious. Consider tighter stops."
            return message, "MEDIUM"
        
        message = f"📅 *UPCOMING:* {upcoming[0]['event']} in {upcoming[0]['hours_until']} hours"
        return message, "LOW"
    
    return "Economic calendar not verified by a live authoritative feed. Check your trading calendar before entry.", "UNVERIFIED"


def display_news_calendar():
    """Display upcoming events for next 14 days"""
    now = datetime.now()
    cutoff = now + timedelta(days=14)
    
    print("\n📅 ECONOMIC CALENDAR - Next 14 Days")
    print("=" * 50)
    
    upcoming_events = []
    for event in HIGH_IMPACT_EVENTS:
        event_date = datetime.strptime(event["date"], "%Y-%m-%d")
        if now <= event_date <= cutoff:
            upcoming_events.append(event)
    
    if not upcoming_events:
        print("No major events scheduled.")
        return
    
    for event in sorted(upcoming_events, key=lambda x: x["date"]):
        impact_icon = "🔴" if event["impact"] == "HIGH" else "🟡"
        print(f"{impact_icon} {event['date']} | {event['time']} | {event['event']}")


def get_event_tags():
    """Get tags for current trade context (for Trade DNA)"""
    active, upcoming = check_upcoming_events()
    tags = []
    
    now = datetime.now()
    hour = now.hour
    
    if hour < 12:
        tags.append("Morning Session")
    elif hour < 17:
        tags.append("Afternoon Session")
    else:
        tags.append("Evening Session")
    
    if active:
        for event in active:
            if "FOMC" in event["event"]:
                tags.append("FOMC Day")
            elif "CPI" in event["event"]:
                tags.append("CPI Day")
            elif "NFP" in event["event"]:
                tags.append("NFP Day")
            elif "PPI" in event["event"]:
                tags.append("PPI Day")
            elif "GDP" in event["event"]:
                tags.append("GDP Day")
    
    return tags


if __name__ == "__main__":
    print("=== News Intelligence Engine ===\n")
    
    # Check for active warnings
    warning, level = generate_news_warning()
    print(f"News Status: {level}")
    print(warning)
    
    # Confidence adjustment
    adj = get_confidence_adjustment()
    print(f"\nConfidence Adjustment: {adj}%")
    
    # Event tags
    tags = get_event_tags()
    print(f"\nCurrent Session Tags: {', '.join(tags)}")
    
    # Calendar
    display_news_calendar()
