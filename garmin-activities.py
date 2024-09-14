from datetime import datetime, timezone
from garminconnect import Garmin
from notion_client import Client
import pytz
import os

# Your local time zone, replace with the appropriate one if needed
local_tz = pytz.timezone('America/Toronto')

ACTIVITY_ICONS = {
    "Running": "https://img.icons8.com/?size=100&id=k1l1XFkME39t&format=png&color=000000"
    ,"Treadmill Running": "https://img.icons8.com/?size=100&id=9794&format=png&color=000000"
    ,"Cycling": "https://img.icons8.com/?size=100&id=47443&format=png&color=000000"
    ,"Indoor Cycling": "https://img.icons8.com/?size=100&id=47443&format=png&color=000000"
    ,"Swimming": "https://img.icons8.com/?size=100&id=9777&format=png&color=000000"
    ,"Strength Training": "https://img.icons8.com/?size=100&id=62779&format=png&color=000000"
    ,"Walking": "https://img.icons8.com/?size=100&id=9807&format=png&color=000000"
    ,"Yoga": "https://img.icons8.com/?size=100&id=9783&format=png&color=000000"
    ,"Hiking": "https://img.icons8.com/?size=100&id=9844&format=png&color=000000"
    ,"Rowing": "https://img.icons8.com/?size=100&id=24889&format=png&color=000000"
    # Add more mappings as needed
}

def get_all_activities(garmin, limit=1000):
    return garmin.get_activities(0, limit)

def format_activity_type(activity_type):
    return activity_type.replace('_', ' ').title()

def format_entertainment(activity_name):
    return activity_name.replace('ENTERTAINMENT', 'Netflix')

def format_training_message(message):
    messages = {
        'NO_': 'No Benefit',
        'MINOR_': 'Some Benefit',
        'RECOVERY_': 'Recovery',
        'MAINTAINING_': 'Maintaining',
        'IMPROVING_': 'Improving',
        'IMPACTING_': 'Impacting',
        'HIGHLY_': 'Highly Impacting',
        'OVERREACHING_': 'Overreaching'
    }
    for key, value in messages.items():
        if message.startswith(key):
            return value
    return message

def format_training_effect(trainingEffect_label):
    return trainingEffect_label.replace('_', ' ').title()

def format_pace(average_speed):
    if average_speed > 0:
        pace_min_km = 1000 / (average_speed * 60)  # Convert to min/km
        minutes = int(pace_min_km)
        seconds = int((pace_min_km - minutes) * 60)
        return f"{minutes}:{seconds:02d} min/km"
    else:
        return ""

def activity_exists(client, database_id, activity_date, activity_type, activity_name):
    """
    Check if an activity already exists in the Notion database and return it if found.
    """
    query = client.databases.query(
        database_id=database_id,
        filter={
            "and": [
                {"property": "Date", "date": {"equals": activity_date.split('T')[0]}},
                {"property": "Activity Type", "select": {"equals": activity_type}},
                {"property": "Activity Name", "title": {"equals": activity_name}}
            ]
        }
    )
    results = query['results']
    return results[0] if results else None

def activity_needs_update(existing_activity, new_activity):
    """
    Compare existing activity with new activity data to determine if an update is needed.
    """
    existing_props = existing_activity['properties']
    return (
        existing_props['Distance (km)']['number'] != round(new_activity.get('distance', 0) / 1000, 2) or
        existing_props['Duration (min)']['number'] != round(new_activity.get('duration', 0) / 60, 2) or
        existing_props['Calories']['number'] != new_activity.get('calories', 0) or
        existing_props['Avg Pace']['rich_text'][0]['text']['content'] != format_pace(new_activity.get('averageSpeed', 0)) or
        existing_props['Training Effect']['select']['name'] != format_training_effect(new_activity.get('trainingEffectLabel', 'Unknown')) or
        existing_props['Aerobic']['number'] != round(new_activity.get('aerobicTrainingEffect', 1)) or
        existing_props['Aerobic Effect']['select']['name'] != format_training_message(new_activity.get('aerobicTrainingEffectMessage', 'Unknown')) or
        existing_props['Anaerobic']['number'] != round(new_activity.get('anaerobicTrainingEffect', 1)) or
        existing_props['Anaerobic Effect']['select']['name'] != format_training_message(new_activity.get('anaerobicTrainingEffectMessage', 'Unknown')) or
        existing_props['PR']['checkbox'] != new_activity.get('pr', False)
    )

def update_activity(client, existing_activity, new_activity):
    """
    Update an existing activity in the Notion database with new data.
    """
    client.pages.update(
        page_id=existing_activity['id'],
        properties={
            "Distance (km)": {"number": round(new_activity.get('distance', 0) / 1000, 2)},
            "Duration (min)": {"number": round(new_activity.get('duration', 0) / 60, 2)},
            "Calories": {"number": new_activity.get('calories', 0)},
            "Avg Pace": {"rich_text": [{"text": {"content": format_pace(new_activity.get('averageSpeed', 0))}}]},
            "Training Effect": {"select": {"name": format_training_effect(new_activity.get('trainingEffectLabel', 'Unknown'))}},
            "Aerobic": {"number": round(new_activity.get('aerobicTrainingEffect', 1))},
            "Aerobic Effect": {"select": {"name": format_training_message(new_activity.get('aerobicTrainingEffectMessage', 'Unknown'))}},
            "Anaerobic": {"number": round(new_activity.get('anaerobicTrainingEffect', 1))},
            "Anaerobic Effect": {"select": {"name": format_training_message(new_activity.get('anaerobicTrainingEffectMessage', 'Unknown'))}},
            "PR": {"checkbox": new_activity.get('pr', False)}
        }
    )

def create_activity(client, database_id, activity):
    """
    Create a new activity in the Notion database.
    """
    activity_date = activity.get('startTimeGMT')
    activity_type = format_activity_type(activity.get('activityType', {}).get('typeKey', 'Unknown'))
    activity_name = format_entertainment(activity.get('activityName', 'Unnamed Activity'))
    
    # Get icon for the activity type
    icon_url = ACTIVITY_ICONS.get(activity_type)
    
    properties = {
        "Date": {"date": {"start": activity_date}},
        "Activity Type": {"select": {"name": activity_type}},
        "Activity Name": {"title": [{"text": {"content": activity_name}}]},
        "Distance (km)": {"number": round(activity.get('distance', 0) / 1000, 2)},
        "Duration (min)": {"number": round(activity.get('duration', 0) / 60, 2)},
        "Calories": {"number": activity.get('calories', 0)},
        "Avg Pace": {"rich_text": [{"text": {"content": format_pace(activity.get('averageSpeed', 0))}}]},
        "Training Effect": {"select": {"name": format_training_effect(activity.get('trainingEffectLabel', 'Unknown'))}},
        "Aerobic": {"number": round(activity.get('aerobicTrainingEffect', 1))},
        "Aerobic Effect": {"select": {"name": format_training_message(activity.get('aerobicTrainingEffectMessage', 'Unknown'))}},
        "Anaerobic": {"number": round(activity.get('anaerobicTrainingEffect', 1))},
        "Anaerobic Effect": {"select": {"name": format_training_message(activity.get('anaerobicTrainingEffectMessage', 'Unknown'))}},
        "PR": {"checkbox": activity.get('pr', False)}
    }
    
    page = {
        "parent": {"database_id": database_id},
        "properties": properties,
    }
    
    if icon_url:
        page["icon"] = {"type": "external", "external": {"url": icon_url}}
    
    client.pages.create(**page)

def update_activity(client, existing_activity, new_activity):
    """
    Update an existing activity in the Notion database with new data.
    """
    activity_type = format_activity_type(new_activity.get('activityType', {}).get('typeKey', 'Unknown'))
    
    # Get icon for the activity type
    icon_url = ACTIVITY_ICONS.get(activity_type)
    
    properties = {
        "Distance (km)": {"number": round(new_activity.get('distance', 0) / 1000, 2)},
        "Duration (min)": {"number": round(new_activity.get('duration', 0) / 60, 2)},
        "Calories": {"number": new_activity.get('calories', 0)},
        "Avg Pace": {"rich_text": [{"text": {"content": format_pace(new_activity.get('averageSpeed', 0))}}]},
        "Training Effect": {"select": {"name": format_training_effect(new_activity.get('trainingEffectLabel', 'Unknown'))}},
        "Aerobic": {"number": round(new_activity.get('aerobicTrainingEffect', 1))},
        "Aerobic Effect": {"select": {"name": format_training_message(new_activity.get('aerobicTrainingEffectMessage', 'Unknown'))}},
        "Anaerobic": {"number": round(new_activity.get('anaerobicTrainingEffect', 1))},
        "Anaerobic Effect": {"select": {"name": format_training_message(new_activity.get('anaerobicTrainingEffectMessage', 'Unknown'))}},
        "PR": {"checkbox": new_activity.get('pr', False)}
    }
    
    update = {
        "page_id": existing_activity['id'],
        "properties": properties,
    }
    
    if icon_url:
        update["icon"] = {"type": "external", "external": {"url": icon_url}}
        
    client.pages.update(**update)

def main():
    # Initialize Garmin and Notion clients using environment variables
    garmin_email = os.getenv("GARMIN_EMAIL")
    garmin_password = os.getenv("GARMIN_PASSWORD")
    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DB_ID")

    # Initialize Garmin client and login
    garmin = Garmin(garmin_email, garmin_password)
    garmin.login()
    client = Client(auth=notion_token)
    
    # Get all activities
    activities = get_all_activities(garmin)

    # Process all activities
    for activity in activities:
        activity_date = activity.get('startTimeGMT')
        activity_type = format_activity_type(activity.get('activityType', {}).get('typeKey', 'Unknown'))
        activity_name = format_entertainment(activity.get('activityName', 'Unnamed Activity'))
        
        # Check if activity already exists in Notion
        existing_activity = activity_exists(client, database_id, activity_date, activity_type, activity_name)
        
        if existing_activity:
            if activity_needs_update(existing_activity, activity):
                update_activity(client, existing_activity, activity)
                print(f"Updated: {activity_type} - {activity_name}")
        else:
            create_activity(client, database_id, activity)
            print(f"Created: {activity_type} - {activity_name}")

if __name__ == '__main__':
    main()
