from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory
import firebase_admin
import requests
from firebase_admin import credentials, auth, firestore
import os
from dotenv import load_dotenv
import base64
import io
from PIL import Image # Need to install Pillow
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from google.cloud import vision
from food_classifier import predict_from_base64

# Load environment variables
load_dotenv()

# Get API keys from environment variables with default values
FIREBASE_WEB_API_KEY = os.getenv('FIREBASE_WEB_API_KEY', 'AIzaSyB-irUwNFidbPmVzIdPNxGjMivu-jHtZps')
GOOGLE_PLACES_API_KEY = os.getenv('GOOGLE_PLACES_API_KEY', 'AIzaSyDwiDXbc4-SEYCGvLdQY-cu8Tagv5xbObk')

# Verify that API keys are set
if not FIREBASE_WEB_API_KEY or not GOOGLE_PLACES_API_KEY:
    raise ValueError("Missing required API keys in environment variables")

# aplicatie Flask
app = Flask(__name__)
app.secret_key = 'cheie' 
app.permanent_session_lifetime = 86400  # 24 hours default session lifetime

cred = credentials.Certificate("C:/Users/manda/CalorieVisor/calorievisor-firebase-adminsdk-25pjr.json")

firebase_admin.initialize_app(cred)

# Initialize Firestore DB client
try:
    db = firestore.client()
except Exception as e:
    print(f"Warning: Failed to initialize Firestore client: {e}")
    db = None

# Initialize Google Cloud Vision client
vision_client = vision.ImageAnnotatorClient()

# Nutritionix API configuration
NUTRITIONIX_APP_ID = os.getenv('NUTRITIONIX_APP_ID')
NUTRITIONIX_API_KEY = os.getenv('NUTRITIONIX_API_KEY')

# Edamam API configuration
EDAMAM_APP_ID = os.getenv('EDAMAM_APP_ID')
EDAMAM_APP_KEY = os.getenv('EDAMAM_APP_KEY')

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def map_to_nutritionix(label):
    # Nutritionix expects lowercase, space-separated names
    return label.replace('_', ' ').lower()

# redirect login
@app.route("/")
def home():
    return redirect(url_for('login'))

# ruta pagina login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember') == 'on'  # Check if remember me was checked

        if not email or not password:
            return render_template("login.html", error="Please enter both email and password.")

        # validare parola
        try:
            response = requests.post(
                f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}",
                json={"email": email, "password": password, "returnSecureToken": True},
            )
            response_data = response.json()

            if "error" in response_data:
                error_message = response_data["error"]["message"]
                return render_template("login.html", error=f"Login failed: {error_message}")

            # Set session to be permanent if remember me is checked
            if remember:
                session.permanent = True
                app.permanent_session_lifetime = 30 * 86400  # 30 days for remembered sessions
            else:
                session.permanent = False
                app.permanent_session_lifetime = 86400  # 24 hours for regular sessions

            session['user'] = email 
            return redirect(url_for('home_page'))
        except requests.RequestException as e:
            return render_template("login.html", error=f"An error occurred: {str(e)}")
    
    # Check if user is already logged in for auto-redirect
    if 'user' in session:
        return redirect(url_for('home_page'))
        
    return render_template("login.html")

# ruta pagina de signup
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form.get('email')  
        password = request.form.get('password')
        reenter_password = request.form.get('reenter_password')
        
        if not email or not password or not reenter_password:
            return render_template("signup.html", error="All fields are required.")
        
        if password != reenter_password:
            return render_template("signup.html", error="Passwords do not match.")
        
        try:
            # creare user
            user = auth.create_user(email=email, password=password)
            session['user'] = user.email  
            return redirect(url_for('home_page'))
        except firebase_admin.exceptions.FirebaseError as e:
            return render_template("signup.html", error=f"Error creating user: {e}")
    return render_template("signup.html")


# ruta home
@app.route("/home")
def home_page():
    if 'user' not in session:
        return redirect(url_for('login'))  
    return render_template("home.html")

# ruta logout
@app.route("/logout")
def logout():
    session.pop('user', None)  
    flash("You have been successfully logged out", "info")
    return redirect(url_for('login'))

@app.route("/nearest_gym")
def nearest_gym():
    if 'user' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))
    # Pass the API key to the template
    return render_template("nearest_gym.html", maps_api_key=GOOGLE_PLACES_API_KEY)

@app.route("/api/nearby_gyms", methods=["GET"])
def nearby_gyms():
    if 'user' not in session:
        return jsonify({"error": "Unauthorized"}), 401
    
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    
    if not lat or not lng:
        return jsonify({"error": "Missing location parameters"}), 400
    
    try:
        # Google Places API request
        url = f"https://maps.googleapis.com/maps/api/place/nearbysearch/json"
        params = {
            "location": f"{lat},{lng}",
            "radius": 5000,  # 5km radius
            "type": "gym",
            "key": GOOGLE_PLACES_API_KEY
        }
        
        response = requests.get(url, params=params)
        data = response.json()
        
        if data.get("status") != "OK":
            return jsonify({"error": "Failed to fetch gyms"}), 500
        
        # Extract relevant gym information
        gyms = []
        for place in data.get("results", [])[:3]:  # Get top 3 gyms
            gym = {
                "name": place.get("name"),
                "address": place.get("vicinity"),
                "rating": place.get("rating"),
                "location": place.get("geometry", {}).get("location")
            }
            gyms.append(gym)
        
        return jsonify({"gyms": gyms})
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/profile", methods=['GET', 'POST'])
def profile():
    if 'user' not in session:
        flash("Please log in to view your profile.", "warning")
        return redirect(url_for('login'))
    
    if not db:
        flash("Database connection error. Please try again later.", "danger")
        return render_template("profile.html", user_email=session.get('user'))

    user_email = session.get('user')
    profile_doc_ref = db.collection('userProfiles').document(user_email)
    
    if request.method == 'POST':
        try:
            # Convert form values, ensuring correct types
            age_val = request.form.get('age')
            height_val = request.form.get('height')
            weight_val = request.form.get('weight')

            profile_data = {
                'name': request.form.get('name', '').strip(),
                'gender': request.form.get('gender'),
                'age': int(age_val) if age_val else None,
                'height': int(height_val) if height_val else None,
                'weight': float(weight_val) if weight_val else None,
                'activity_level': request.form.get('activity_level'),
                'body_type': request.form.get('body_type'),
                'goal': request.form.get('goal')
            }
            profile_data = {k: v for k, v in profile_data.items() if v is not None and v != ''}

            if not profile_data:
                 flash("No profile data submitted.", "warning")
                 return redirect(url_for('profile'))

            profile_doc_ref.set(profile_data, merge=True) 
            flash("Profile updated successfully!", "success")
            
        except ValueError:
             flash("Invalid input for age, height, or weight. Please enter numbers.", "danger")
        except Exception as e:
            flash(f"An error occurred while updating profile: {e}", "danger")
            print(f"Error updating profile for {user_email}: {e}")

        return redirect(url_for('profile'))

    # GET request: Load existing profile data
    user_profile = {}
    try:
        doc = profile_doc_ref.get()
        if doc.exists:
            user_profile = doc.to_dict()
    except Exception as e:
         flash(f"An error occurred while fetching profile: {e}", "danger")
         print(f"Error fetching profile for {user_email}: {e}")

    return render_template(
        "profile.html", 
        user_email=user_email, 
        profile=user_profile
    )

# Second fuctinality
def calculate_nutrition_needs(profile_data):
    try:
        # Extract data with defaults
        age = int(profile_data.get('age', 30))
        weight_kg = float(profile_data.get('weight', 70))
        height_cm = int(profile_data.get('height', 170))
        gender = profile_data.get('gender', 'male').lower()
        activity_level = profile_data.get('activity_level', 'light')
        goal = profile_data.get('goal', 'maintain')


        # --- Harris-Benedict BMR Calculation --- 
        if gender == 'male':
            bmr = 88.362 + (13.397 * weight_kg) + (4.799 * height_cm) - (5.677 * age)
        elif gender == 'female':
            bmr = 447.593 + (9.247 * weight_kg) + (3.098 * height_cm) - (4.330 * age)
        else:
            # Default to male formula or average if gender not specified/other
            bmr = 88.362 + (13.397 * weight_kg) + (4.799 * height_cm) - (5.677 * age)
            
        # --- Activity Factor --- 
        activity_multipliers = {
            'sedentary': 1.2,
            'light': 1.375,
            'moderate': 1.55,
            'very': 1.725,
            'extra': 1.9
        }
        activity_factor = activity_multipliers.get(activity_level, 1.375) # Default to light
        
        # --- TDEE (Total Daily Energy Expenditure) ---
        tdee = bmr * activity_factor
        
        # --- Adjust Calories Based on Goal --- 
        calorie_adjustments = {
            'lose_weight': -500, # Deficit
            'maintain': 0,
            'build_muscle': 300  # Surplus
        }
        target_calories = tdee + calorie_adjustments.get(goal, 0)
        # Ensure minimum calories (e.g., 1200) - adjust as needed
        target_calories = max(1200, target_calories)
            
        # --- Define Macro Splits based on Goal (Example Ratios P/C/F) --- 
        macro_splits = {
            'lose_weight': {'p': 0.40, 'c': 0.30, 'f': 0.30},
            'maintain':    {'p': 0.30, 'c': 0.40, 'f': 0.30},
            'build_muscle':{'p': 0.35, 'c': 0.45, 'f': 0.20}
        }
        split = macro_splits.get(goal, macro_splits['maintain']) # Default to maintain

        # --- Calculate Macros in Grams ---
        # 1g Protein = 4 kcal, 1g Carb = 4 kcal, 1g Fat = 9 kcal
        protein_g = (target_calories * split['p']) / 4
        carbs_g = (target_calories * split['c']) / 4
        fat_g = (target_calories * split['f']) / 9
        
        # --- Suggested Sugar Limit (e.g., <10% of total calories) ---
        sugar_g = (target_calories * 0.10) / 4 

        return {
            "target_calories": round(target_calories),
            "protein_g": round(protein_g),
            "carbs_g": round(carbs_g),
            "fat_g": round(fat_g),
            "sugar_g": round(sugar_g) 
        }
    except (ValueError, TypeError, KeyError) as e:
        # Handle potential errors if profile data is missing or invalid type
        print(f"Error during calculation: {e}. Profile data: {profile_data}")
        return None # Indicate calculation failure

@app.route("/personalized_meal_plan")
def personalized_meal_plan():
    if 'user' not in session:
        flash("Please log in to view your meal plan.", "warning")
        return redirect(url_for('login'))
    
    if not db:
        flash("Database connection error. Please try again later.", "danger")
        return redirect(url_for('home_page')) # Redirect home if DB error

    user_email = session.get('user')
    profile_doc_ref = db.collection('userProfiles').document(user_email)
    
    user_profile = {}
    targets = None
    error_message = None

    try:
        doc = profile_doc_ref.get()
        if doc.exists:
            user_profile = doc.to_dict()
            # Check if ALL required data exists for calculation
            required_fields = ['age', 'weight', 'height', 'gender', 'activity_level', 'goal']
            if all(field in user_profile and user_profile[field] is not None for field in required_fields):
                 targets = calculate_nutrition_needs(user_profile)
                 if targets is None: # Check if calculation itself failed
                      error_message = "Calculation failed. Please ensure profile data is valid."
            else:
                missing = [field for field in required_fields if field not in user_profile or user_profile[field] is None]
                error_message = f"Please complete your profile ({', '.join(missing).replace('_',' ').title()}) to calculate your plan."
        else:
            error_message = "Please complete your profile first."
            
    except Exception as e:
        error_message = f"An error occurred: {e}"
        print(f"Error fetching profile/calculating plan for {user_email}: {e}")

    if error_message:
         flash(error_message, "warning")

    return render_template("meal_plan.html", targets=targets, error=error_message)

def get_food_nutrition(food_name):
    """Get nutritional information from Nutritionix API"""
    url = "https://trackapi.nutritionix.com/v2/natural/nutrients"
    headers = {
        "x-app-id": NUTRITIONIX_APP_ID,
        "x-app-key": NUTRITIONIX_API_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "query": food_name
    }
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        if 'foods' in result and len(result['foods']) > 0:
            food = result['foods'][0]
            return {
                'name': food['food_name'],
                'calories': food['nf_calories'],
                'protein': food['nf_protein'],
                'carbs': food['nf_total_carbohydrate'],
                'sugar': food['nf_sugars'],
                'fats': food['nf_total_fat']
            }
    except Exception as e:
        print(f"Error getting nutrition data: {str(e)}")
    return None

@app.route("/api/analyze_food", methods=['POST'])
def analyze_food():
    if 'user' not in session:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.get_json()
    if not data or 'image_base64' not in data:
        return jsonify({"success": False, "error": "Missing image_base64 data"}), 400

    image_base64 = data['image_base64']

    try:
        # Use local classifier to predict food label
        food_item = predict_from_base64(image_base64)
        if not food_item:
            return jsonify({"success": False, "error": "No food detected in the image"}), 400

        # Map to Nutritionix-friendly name
        mapped_food_item = map_to_nutritionix(food_item.split('(')[0].strip())

        # Get nutrition data for the detected food
        nutrition_data = get_food_nutrition(mapped_food_item)
        if not nutrition_data:
            nutrition_facts = {
                "name": food_item,
                "calories": 100,
                "protein_g": 2,
                "fat_total_g": 1,
                "carbohydrate_total_g": 20,
                "sugars_g": 5
            }
        else:
            nutrition_facts = {
                "name": nutrition_data.get('name', food_item),
                "calories": nutrition_data['calories'],
                "protein_g": nutrition_data['protein'],
                "fat_total_g": nutrition_data['fats'],
                "carbohydrate_total_g": nutrition_data['carbs'],
                "sugars_g": nutrition_data['sugar']
            }

        return jsonify({
            "success": True,
            "food_item": food_item,
            "nutrition_facts": nutrition_facts
        })

    except Exception as e:
        print(f"Error processing image: {e}")
        return jsonify({"success": False, "error": f"Error processing image: {str(e)}"}), 500

@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if request.method == "POST":
        email = request.form.get('email')
        
        if not email:
            return render_template("reset_password.html", error="Please enter your email address.")
        
        try:
            # Generate a password reset link using Firebase Auth
            reset_link = auth.generate_password_reset_link(email)
            
            # In a real application, you would send an email with the reset link
            # For now, we'll just display it in the UI
            return render_template("reset_password.html", 
                                   success=True, 
                                   message="Password reset link has been generated.", 
                                   reset_link=reset_link)
        except firebase_admin.exceptions.FirebaseError as e:
            return render_template("reset_password.html", error=f"Error: {e}")
    
    return render_template("reset_password.html")

# Social login routes
@app.route("/login/facebook")
def facebook_login():
    # In a real application, you would redirect to Facebook OAuth authorization URL
    # For now, we'll just redirect back to login with a message
    flash("Facebook login is not implemented yet.", "info")
    return redirect(url_for('login'))

@app.route("/login/google")
def google_login():
    # In a real application, you would redirect to Google OAuth authorization URL
    # For now, we'll just redirect back to login with a message
    flash("Google login is not implemented yet.", "info")
    return redirect(url_for('login'))

@app.route("/login/apple")
def apple_login():
    # In a real application, you would redirect to Apple OAuth authorization URL
    # For now, we'll just redirect back to login with a message
    flash("Apple login is not implemented yet.", "info")
    return redirect(url_for('login'))

# Add route for favicon.ico
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

# Add route for robots.txt
@app.route('/robots.txt')
def robots():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'robots.txt', mimetype='text/plain')

# Add route for manifest
@app.route('/site.webmanifest')
def manifest():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'site.webmanifest', mimetype='application/manifest+json')

def detect_food(image_path):
    """Detect food items in the image using Google Cloud Vision API"""
    try:
        with open(image_path, 'rb') as image_file:
            content = image_file.read()
        
        image = vision.Image(content=content)
        response = vision_client.label_detection(image=image)
        labels = response.label_annotations
        
        # Filter for food-related labels
        food_labels = [label.description for label in labels 
                      if any(food_term in label.description.lower() 
                            for food_term in ['food', 'dish', 'meal', 'fruit', 'vegetable', 'meat'])]
        
        return food_labels[0] if food_labels else None
        
    except Exception as e:
        print(f"Error detecting food: {str(e)}")
        return None

# Food scanning route
@app.route("/scan-food", methods=['GET', 'POST'])
def scan_food():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        is_ajax = request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if 'food_image' not in request.files:
            if is_ajax:
                return jsonify({'success': False, 'error': 'No image uploaded'}), 400
            flash('No image uploaded', 'error')
            return redirect(request.url)
        
        file = request.files['food_image']
        if file.filename == '':
            if is_ajax:
                return jsonify({'success': False, 'error': 'No image selected'}), 400
            flash('No image selected', 'error')
            return redirect(request.url)
        
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            try:
                food_name = detect_food(filepath)
                if food_name:
                    nutrition_data = get_food_nutrition(food_name)
                    if nutrition_data:
                        os.remove(filepath)
                        if is_ajax:
                            return jsonify({'success': True})
                        return render_template('scan_result.html', 
                                             nutrition=nutrition_data,
                                             user=session['user'])
                    else:
                        if is_ajax:
                            return jsonify({'success': False, 'error': 'Could not get nutritional information for the detected food'}), 400
                        flash('Could not get nutritional information for the detected food', 'error')
                else:
                    if is_ajax:
                        return jsonify({'success': False, 'error': 'No food detected in the image'}), 400
                    flash('No food detected in the image', 'error')
            except Exception as e:
                if is_ajax:
                    return jsonify({'success': False, 'error': f'Error processing image: {str(e)}'}), 500
                flash(f'Error processing image: {str(e)}', 'error')
            if os.path.exists(filepath):
                os.remove(filepath)
            if is_ajax:
                return jsonify({'success': False, 'error': 'Unknown error occurred'}), 500
            return redirect(request.url)
    return render_template('scan_food.html', user=session['user'])

# lanseaza aplicatie flask
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
