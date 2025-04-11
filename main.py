import datetime

from flask import Flask, request, jsonify
import json
import pytz
from pyairtable import Api
from pyairtable.formulas import match

app = Flask(__name__)
####################################################################################
####################################################################################

# Example: Converts a Unix timestamp string to ISO 8601 in IST (UTC+5:30)
def timestamp_to_iso8601_plus_530(timestamp_str):
    dt_utc = datetime.datetime.fromtimestamp(float(timestamp_str), tz=datetime.timezone.utc)
    ist = pytz.timezone('Asia/Kolkata')
    dt_ist = dt_utc.astimezone(ist)
    return dt_ist.isoformat()

# Example: Gets the current datetime in ISO 8601 format (using IST)
def get_current_datetime_iso8601():
    ist = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.datetime.now(ist)
    return now_ist.isoformat()

# Example: Calculates time difference between two ISO 8601 strings in seconds
def calculate_time_difference_seconds(start_iso, end_iso):
    start_dt = datetime.datetime.fromisoformat(start_iso)
    end_dt = datetime.datetime.fromisoformat(end_iso)
    # Ensure both are offset-aware or both naive for comparison
    # If one has timezone and other doesn't, handle appropriately (e.g., make both UTC)
    # This simple subtraction works if they are from the same timezone source (like our examples)
    time_diff = end_dt - start_dt
    return time_diff.total_seconds()

####################################################################################
####################################################################################


YOUR_API_KEY = "pattnctX4txlc8VX4.1852d01eeb0edd92b611207327978691d0391e26515a31e805c18e07d8b5ef63"
YOUR_BASE_ID = "appEI61LsVlpN3JcB"
YOUR_TABLE_NAME = "Radiance" # Or specify a different table if user data is separate

# --- IMPORTANT: Define your Airtable Field Names for User Data ---
# Replace these with the EXACT names of the columns (fields) in your Airtable table
# Reuse names from previous examples where applicable


@app.route('/user_check_airtable', methods=['POST']) # Changed route slightly
def user_check_airtable():
    data = request.get_json()

    FIELD_USERNAME = "userName"          # Example field name for userName
    FIELD_USER_ID = "id"            # Example field name for Id (THIS IS THE FIELD TO SEARCH)
    FIELD_REGISTRATION_TIME = "registrationTime" # Example (used if user not found)
    FIELD_AUTHORISED_FLAG = "permission" # Example field name for the "yes"/"no" check (index 3)
    FIELD_DAILY_COUNTER = "callsToday"   # Example field name for the counter (index 4)
    FIELD_LAST_CHECK_TIME = "lastCallAt"
    
    # ----------------------------------------------------
    # Configuration
    DAILY_LIMIT = 50


    if not data:
        return ("error-Invalid JSON payload")

    try:
        # Extract data from the request
        id_to_find = data.get('id')
        user_name = data.get('userName') # Needed if user has to be created

        if not id_to_find:
            return ("error-Missing required field in JSON payload: ID")
        # userName is only strictly needed if the user might not exist, but get it anyway
        if not user_name:
            return ("error-Missing required field in JSON payload: userName")

        # Initialize Airtable API client and table
        airtable_api = Api(YOUR_API_KEY)
        airtable_table = airtable_api.table(YOUR_BASE_ID, YOUR_TABLE_NAME)

        # --- Find the user record ---
        formula = match({"id": id_to_find})
        found_record = airtable_table.first(formula=formula)

        if not found_record:
            # User not found - create them (similar to register_user) and return "Not Authorised"
            print(f"User ID '{id_to_find}' not found. Creating new record.")
            current_time_iso = get_current_datetime_iso8601()
            
            new_record_data = {
                "userName": user_name,
                "id": id_to_find,
                "registrationTime": current_time_iso, # First timestamp
                "permission": "no",                     # Default flag value
                "callsToday": 0,                      # Default number value
                "lastCallAt": current_time_iso,
                "userType": "Radiance"   # Second timestamp (same as registration initially)
            }
            try:
                airtable_table.create(new_record_data)
            except Exception as create_e:
                 print(f"Error creating new user record: {create_e}")
                 # Decide if you still return "Not Authorised" or a specific creation error
            return ("Not Authorised") # 403 Forbidden is appropriate

        else:
            # User found - proceed with checks and potential update
            record_id = found_record['id']
            fields = found_record['fields']
            print(f"Found user ID '{id_to_find}' in record {record_id}.")

            # 1. Check Authorisation Flag (Field at original index 3)
            is_authorised = fields.get(FIELD_AUTHORISED_FLAG) == "yes"
            if not is_authorised:
                print(f"User {id_to_find} is not authorised (Flag is not 'yes').")
                return ("Not Authorised")

            # Prepare fields to update
            fields_to_update = {}
            needs_update = False

            # 2. Check Date and Counter (Fields at original indices 5 and 4)
            last_check_time_str = fields.get(FIELD_LAST_CHECK_TIME)
            current_counter = int(fields.get(FIELD_DAILY_COUNTER, 0)) # Default to 0 if missing, ensure int

            # Get today's date - use timezone consistent with stored times if necessary
            # If storing naive times, use datetime.date.today()
            # If storing timezone-aware (like IST from helper), get today in that zone
            today = datetime.datetime.now(pytz.timezone('Asia/Kolkata')).date() # Use same timezone as helper
            # today = datetime.date.today() # Use this if your times are naive

            update_counter = current_counter # Start with current value

            
            
            try:
                if last_check_time_str.endswith('Z'):
                    last_check_time_str = last_check_time_str[:-1] + '+00:00'
                last_check_dt = datetime.datetime.fromisoformat(last_check_time_str)
                # Compare dates (ignoring time)
                if last_check_dt.date() != today:
                    update_counter = 1 # Reset counter for the new day
                    needs_update = True
                else:
                    # Same day, check limit and increment
                    if current_counter >= DAILY_LIMIT:
                        
                        print(f"User {id_to_find} exceeded daily limit of {DAILY_LIMIT}.")
                        return ("Limit Exceeded")
                    else:
                        
                        update_counter = current_counter + 1
                        print(f"Incrementing counter for user {id_to_find} to {update_counter}.")
                        needs_update = True

            except Exception as e:
                
                print(f"Error parsing last check time '{last_check_time_str}'. Resetting counter.")
                update_counter = 1 # Treat as first check today if date is invalid
                needs_update = True

            # 3. Prepare Update Payload (only if counter changed) and always update timestamp
            if needs_update:
                 fields_to_update[FIELD_DAILY_COUNTER] = update_counter

            # Always update the last check time (Field at original index 5)
            new_check_time = get_current_datetime_iso8601()
            fields_to_update[FIELD_LAST_CHECK_TIME] = new_check_time
            fields_to_update["userType"] = "Radiance"

            needs_update = True # Ensure we always update the timestamp

            # 4. Perform Update if necessary
            if needs_update:
                print(f"Updating record {record_id} with: {fields_to_update}")
                airtable_table.update(record_id, fields_to_update)
                print(f"Successfully updated record {record_id}.")
            else:
                 print(f"No counter update needed for record {record_id}, but timestamp updated implicitly if code reaches here.")
                 # If you only wanted to update timestamp *if* counter changed, adjust logic above

            return ("Normal")

    except:
        return('error')


@app.route('/record_results_airtable', methods=['POST']) # Changed route slightly
def record_results_airtable():
    data = request.get_json()
    YOUR_TABLE_NAME = "history"
    
    try:
        # Extract data from the request
        # Note: 'workbook' and 'worksheet' are not needed for Airtable
        start_time_input = data.get('startTime') # Use .get for safer access
        question = data.get('question')
        answer = data.get('answer')
        record_id = data.get('id') # Changed variable name slightly for clarity
        messageFormat=data.get('messageFormat')
        base64ImageString=data.get('base64ImageString')
        tokens=base64ImageString=data.get('tokens')

        # Initialize Airtable API client and table
        airtable_api = Api(YOUR_API_KEY)
        airtable_table = airtable_api.table(YOUR_BASE_ID, YOUR_TABLE_NAME)
        # Process date/time
        start_time_iso = timestamp_to_iso8601_plus_530(str(start_time_input))
        current_datetime_iso = get_current_datetime_iso8601()
        time_diff_seconds = calculate_time_difference_seconds(start_time_iso, current_datetime_iso)


        # Prepare data payload for Airtable record
        # Keys MUST match your Airtable field names EXACTLY
        record_data = {
            "id": record_id,
            "dateTime": current_datetime_iso, # Store as ISO 8601 string
            "responseTime": time_diff_seconds,       # Store as number
            "question": question,
            "answer": answer,
            "tokensUsed": 34,
            "userMessageFormat":messageFormat,
            "base64ImageString":base64ImageString,
            "tokensUsed":tokens
        }

        # Create the new record in Airtable
        airtable_table.create(record_data)

        return("success") # Return JSON success

    except KeyError as e:
        # Handle missing keys in the input JSON more specifically if needed
        return (str(e))


@app.route('/register_user_airtable', methods=['POST']) # Changed route slightly
def register_user_airtable():
    data = request.get_json()
    YOUR_TABLE_NAME="Radiance"
    
    try:
        # Extract data from the request
        # Note: 'workbook' and 'worksheet' are not needed
        user_id = data.get('id')
        user_name = data.get('userName')
        
        # Initialize Airtable API client and table
        airtable_api = Api(YOUR_API_KEY)
        airtable_table = airtable_api.table(YOUR_BASE_ID, YOUR_TABLE_NAME)

        # --- Check if user ID already exists ---
        # We search for a record where the FIELD_USER_ID matches the provided user_id
        # Using table.first() is efficient as we only need to know if at least one exists
        # The 'match' helper creates a formula like: "{User ID} = 'provided_id'"
        formula = match({"id": user_id})
        # print(f"Searching with formula: {formula}") # Optional: for debugging
        existing_record = airtable_table.first(formula=formula)

        if existing_record:
            # User ID found in the table
            return ("userPresent") # Indicate user already exists
        else:
            # User ID not found, create a new record
            current_time_iso = get_current_datetime_iso8601()
            # Prepare data for the new Airtable record
            # Keys MUST match your Airtable field names EXACTLY
            new_record_data = {
                "userName": user_name,
                "id": user_id,
                "registrationTime": current_time_iso, # First timestamp
                "permission": "no",                     # Default flag value
                "callsToday": 0,                      # Default number value
                "lastCallAt": current_time_iso,
                "userType": "Radiance"   # Second timestamp (same as registration initially)
            }
            # Create the new record in Airtable
            airtable_table.create(new_record_data)
            return ("newUser") # Indicate new user created (201 Created status)

    except KeyError as e:
        return ("error")

if __name__ == '__main__':
    app.run() #remove debug=True for production 