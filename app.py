from flask import Flask, render_template, session, redirect, request, url_for, flash, jsonify, send_file
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
import os
from functools import wraps
import random
import replicate
import io
import requests
import base64

load_dotenv()

replicate = replicate.Client(os.environ["REPLICATE_API_TOKEN"])

uri = os.getenv("MONGO_URI_STRING")
client = MongoClient(uri, server_api=ServerApi('1'))
db = client["Accounts"]
userinfo = db["Users"]
logindb = db["Login"]
saved = db["Saved"]
db = client["Images"]
images = db["Images"]
sets = db["Sets"]
public = db["Public"]
app = Flask(__name__)

app.secret_key= "3405gorfejiu84tgfnje2i30rf9joed23rifu90ehoirj49getb8fvu7yd8h3ut4oig9tebifv8dwc7ey80h3ut4og5itu9b0evfdc"


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in") or not session.get("username"):
            flash("You need to be logged in to access this page.")
            return redirect(url_for("login"))
        user = logindb.find_one({"username": session.get("username")})
        if not user:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def gen_random_id():
    rand_id = random.randint(1, 10000)
    if userinfo.find_one({"id": rand_id}):
        return gen_random_id()
    return rand_id

def genRandomImageID():
    rand_id = random.randint(10000, 99999)
    if(images.find_one({"id": rand_id})):
        return genRandomImageID()
    return rand_id

def genRandomSetID():
    rand_id = random.randint(10000, 99999)
    if(sets.find_one({"id": rand_id})):
        return genRandomSetID()
    return rand_id

@app.route("/")
@login_required
def index():
    return render_template("index.html")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        try:
            username = request.form.get("username")
            password = request.form.get("password")
            user = logindb.users.find_one({"username": username})
            if not user:
                logindb.insert_one({
                    "username": username,
                    "password": password,
                })
                return redirect(url_for("login"))
            else:
                return(render_template("error.html"))
        except Exception as e:
            print(e)
            return render_template("error.html")
    return render_template("signup.html", error=None)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form.get("username")
            password = request.form.get("password")
            user = logindb.find_one({"username": username})
            if not user:
                return render_template("login.html", error="User not found.")
            if user["password"] == password:
                session["logged_in"] = True
                session["username"] = username
                return redirect(url_for("index"))
            else:
                return render_template("login.html", error="Wrong password.")
        except:
            return render_template("error.html")
    return render_template("login.html", error=None)

@app.route("/create_set", methods=["GET", "POST"])
def create_set():
    if request.method == "POST":
        prompt_side1 = request.form["prompt_side1"]
        prompt_side2 = request.form["prompt_side2"]
        card_count = int(request.form["card_count"])
        visibility = request.form["visibility"]  # Get visibility

        # Call the generate images function
        return redirect(url_for("generate_images", prompt_side1=prompt_side1, prompt_side2=prompt_side2, card_count=card_count, visibility=visibility))
    
    return render_template("createset.html")



@app.route("/generate_images/<prompt_side1>/<prompt_side2>/<int:card_count>/<visibility>")
def generate_images(prompt_side1, prompt_side2, card_count, visibility):
    # Input for Side 1 (common side for all cards)
    input_side1 = {
        "prompt": prompt_side1,
        "aspect_ratio": "16:9"
    }

    # Generate Side 1
    output_side1 = replicate.run(
        "black-forest-labs/flux-schnell",
        input=input_side1
    )

    # Extract the image URL for Side 1
    url_side1 = output_side1[0]
    response_side1 = requests.get(url_side1)

    if response_side1.status_code != 200:
        flash("Failed to download image for Side 1.")
        return redirect(url_for("create_set"))

    # Save Side 1 image in MongoDB
    image_id_side1 = genRandomImageID()
    image_data_side1 = response_side1.content
    images.insert_one({
        "prompt": prompt_side1,
        "id": image_id_side1,
        "file": image_data_side1
    })

    # Generate and save Side 2 images
    side2_image_ids = []
    for i in range(card_count):
        input_side2 = {
            "prompt": prompt_side2 + f" variation {i+1}",
            "aspect_ratio": "16:9"
        }

        output_side2 = replicate.run(
            "black-forest-labs/flux-schnell",
            input=input_side2
        )

        # Extract the image URL for Side 2
        url_side2 = output_side2[0]
        response_side2 = requests.get(url_side2)

        if response_side2.status_code != 200:
            flash(f"Failed to download image for Side 2 (Card {i+1}).")
            return redirect(url_for("create_set"))

        # Save Side 2 image in MongoDB
        image_id_side2 = genRandomImageID()
        image_data_side2 = response_side2.content
        images.insert_one({
            "prompt": prompt_side2 + f" variation {i+1}",
            "id": image_id_side2,
            "file": image_data_side2
        })

        side2_image_ids.append(image_id_side2)

        # If the card is public, save it to the Public collection
        if visibility == "public":
            public.insert_one({
                "image_id": image_id_side2,
                "side1_id": image_id_side1
            })

    # Create a new set and save the IDs
    set_id = genRandomImageID()  # Assuming you have a function to generate a unique ID
    sets.insert_one({
        "set_id": set_id,
        "side1_id": image_id_side1,
        "side2_ids": side2_image_ids
    })

    # Redirect to view the first image in the set
    return redirect(url_for("view_set", set_id=set_id))



@app.route("/view/<int:id>", methods=["GET", "POST"])
def view_image(id):
    # Retrieve the image from MongoDB using the ID
    image_record = images.find_one({"id": id})
    
    if not image_record:
        return jsonify({"error": "Image not found!"}), 404

    # Handle the "Save" functionality
    if request.method == "POST":
        username = session.get("username")
        if not username:
            flash("You need to be logged in to save an image.")
            return redirect(url_for("login"))

        # Check if the user has already saved the image
        saved_record = saved.find_one({"username": username, "image_id": id})
        if not saved_record:
            # Save the image to the user's saved images collection
            saved.insert_one({
                "username": username,
                "image_id": id
            })
            flash("Image saved successfully!")
        else:
            flash("You've already saved this image.")
        
        return render_template("view_image.html", image_id=id, prompt=image_record["prompt"])

    # Render the template to show the image and save button
    return render_template("view_image.html", image_id=id, prompt=image_record["prompt"])


@app.route("/viewset/<set_id>")
def view_set(set_id):
    # Retrieve the set from the database
    set_data = sets.find_one({"set_id": int(set_id)})
    if not set_data:
        return "Set not found!", 404

    # Retrieve Side 1 and Side 2 images
    side1_image = images.find_one({"id": set_data["side1_id"]})
    side2_images = images.find({"id": {"$in": set_data["side2_ids"]}})

    return render_template("viewset.html", side1_image=side1_image, side2_images=side2_images)

@app.route("/save_card/<set_id>/<side2_image_id>", methods=["POST"])
def save_card(set_id, side2_image_id):
    username = session.get("username")  # Get the logged-in username
    if username:
        # Retrieve the set to get side1
        set_info = sets.find_one({"set_id": int(set_id)})
        if set_info:
            side1 = set_info['side1_id']
            # Save both sides to the Saved collection
            saved.insert_one({
                "username": username,
                "side1": side1,
                "side2_image_id": side2_image_id
            })
            flash("Card saved successfully!")
        else:
            print("Set not found.")
    else:
        flash("You need to be logged in to save cards.")
    return redirect(url_for("browse_cards"))


@app.route("/view_saved")
def view_saved():
    username = session.get("username")
    saved_images = saved.find({"username": username})

    # Debug: Print out the username and number of saved images
    print(f"Username: {username}")

    saved_images_data = []

    for saved_image in saved_images:
        print(f"Saved image data: {saved_image}")  # Debug statement
        
        side1_image_id = saved_image["side1"]
        side2_image_id = saved_image["side2_image_id"]
        
       
        if side1_image_id and side2_image_id:
            saved_images_data.append({
                "side1": side1_image_id,
                "side2": side2_image_id
            })


    return render_template("saved.html", saved_cards=saved_images_data)


@app.route("/serve_image/<int:id>")
def serve_image(id):
    image_record = images.find_one({"id": id})
    
    if not image_record:
        return jsonify({"error": "Image not found!"}), 404

    image_data = io.BytesIO(image_record["file"])

    return send_file(image_data, mimetype='image/png')

@app.route("/browse_cards")
def browse_cards():
    # Get the latest sets from the database
    latest_sets = list(sets.find().sort("_id", -1).limit(10))  # Get the latest 10 sets

    return render_template("browse_cards.html", sets=latest_sets)



if __name__ == "__main__":
    app.run(host='0.0.0.0', port=3945, debug = True)