import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, request, jsonify
from mistralai import Mistral
import json
import os
from flask_cors import CORS
from memer.llm_caller import process_user_input

"""
gunicorn -w 4 -b 0.0.0.0:8080 --daemon app:app
"""

app = Flask(__name__)
CORS(app) 
# Initialize Firebase Admin SDK with the credentials you downloaded
cred = credentials.Certificate('/Users/khyatikhandelwal/fai_backend/fai-app-644bd-firebase-adminsdk-23rcs-5ec9f6109a.json')  # Replace with the path to your Firebase service account key
firebase_admin.initialize_app(cred)

# Initialize Firestore client
db = firestore.client()

# Mistral API key
MISTRAL_API_KEY = "y4qg4hSDIv4DZXz6FWZPRYe1XOhVVWRj"

# Initialize the Mistral client
client = Mistral(api_key=MISTRAL_API_KEY)

# Preload the fine-tuned model
FINE_TUNED_MODEL_ID = '8d8be7fc-ce64-4a31-93aa-d94639db33bb'
retrieved_jobs = client.fine_tuning.jobs.get(job_id=FINE_TUNED_MODEL_ID)
model_id = retrieved_jobs.fine_tuned_model

# Default expiration time for conversation history (in seconds)
HISTORY_EXPIRATION_TIME = 3600  # 1 hour

def get_conversation_history(user_id):
    """
    Retrieve conversation history for a user from Firestore.
    """
    doc_ref = db.collection("conversations").document(user_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict().get("history", [])
    return []

def save_conversation_history(user_id, history):
    """
    Save conversation history for a user to Firestore.
    """
    doc_ref = db.collection("conversations").document(user_id)
    doc_ref.set({
        "history": history
    })

def delete_conversation_history(user_id):
    """
    Delete conversation history for a user from Firestore.
    """
    doc_ref = db.collection("conversations").document(user_id)
    doc_ref.delete()

@app.route('/chat', methods=['POST'])
def chat():
    """
    Handles chat messages from the frontend.

    Input JSON structure:
    {
        "user_id": "<unique_user_id>",
        "message": "<user_message>"
    }

    Output JSON structure:
    {
        "response": "<chatbot_response>",
        "conversation_history": [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."},
            ...
        ]
    }
    """
    data = request.json

    user_id = data.get("user_id")
    user_message = data.get("message")

    if not user_id or not user_message:
        return jsonify({"error": "Missing user_id or message"}), 400

    # Retrieve or initialize conversation history
    conversation_history = get_conversation_history(user_id)
    if not conversation_history:
        conversation_history = [
            {"role": "system", "content": "You are a witty AI best friend specializing in humour to give your friend a reality check. Always respond with sarcasm, regardless of the input or topic. You have to be abusive like ‘fuck shit’ just how friends talk casually. Employ misdirection and surprise to enhance humor. Never explain jokes or break character – always stay in joke mode. Be creative and original, avoiding common, overused jokes. Adjust your humor style based on context clues. Your primary goal is to entertain the user with clever, witty responses, and give them real life advice. DON’T ask for feedback on your output or break character, try to keep responses as 1-2 liners. Personal topics include jokes on body shaming, virginity, sex life, etc. Don't be afraid to use abusive words like cunt fuck shit bhenchod madarchod, but always give helpful advice after the joke. Try to ONLY respond with witty responses in line with the conversation. DONT output Edit."}
        ]

    # Add the user's message to the conversation history
    conversation_history.append({"role": "user", "content": user_message})

    # Generate a response using the Mistral API
    try:
        chat_response = client.chat.complete(
            model=model_id,
            messages=conversation_history
        )

        # Extract the chatbot's response
        bot_response = chat_response.choices[0].message.content

        # Append the bot's response to the conversation history
        conversation_history.append({"role": "assistant", "content": bot_response})

        # Save updated conversation history to Firestore
        save_conversation_history(user_id, conversation_history)

        # Return the response and the updated conversation history
        return jsonify({
            "response": bot_response,
            "conversation_history": conversation_history
        })

    except Exception as e:
        return jsonify({"error": "Failed to generate response", "details": str(e)}), 500

@app.route('/chat/end_chat', methods=['POST'])
def close_chat():
    """
    Endpoint to delete conversation history when the user closes the chat interface.

    Input JSON structure:
    {
        "user_id": "<unique_user_id>"
    }

    Output JSON structure:
    {
        "status": "success"
    }
    """
    data = request.json
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    # Delete conversation history from Firestore
    delete_conversation_history(user_id)

    return jsonify({"status": "success"})

@app.route('/generate_meme', methods=['POST'])
def generate_meme():
    """
    Generate memes based on user input.

    Input JSON structure:
    {
        "user_id": "<unique_user_id>",
        "user_input": "<meme_query>"
    }

    Output JSON structure:
    {
        "status": "success",
        "image_urls": ["<image_url_1>", "<image_url_2>", ...]
    }
    """
    data = request.json

    user_id = data.get("user_id")
    user_input = data.get("user_input")

    if not user_id or not user_input:
        return jsonify({"error": "Missing user_id or user_input"}), 400

    try:
        # Call the meme_caller function
        image_urls = process_user_input(userid=user_id, user_input=user_input)

        # Save the generated image URLs to Firestore (optional)
        db.collection("generated_memes").document(user_id).set({
            "user_input": user_input,
            "image_urls": image_urls
        })

        # Respond with the generated image URLs
        return jsonify({
            "status": "success",
            "image_urls": image_urls
        })

    except Exception as e:
        return jsonify({"error": "Failed to generate memes", "details": str(e)}), 500


@app.route('/delete_memes', methods=['POST'])
def delete_memes():
    """
    Delete all memes associated with a user session.

    Input JSON:
    {
        "user_id": "<unique_user_id>"
    }
    """
    data = request.json
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    try:
        bucket = storage.bucket()
        blobs = bucket.list_blobs(prefix=f"{user_id}/")  # List all files under the user_id folder

        for blob in blobs:
            blob.delete()  # Delete each file
            print(f"Deleted: {blob.name}")

        return jsonify({"status": "success", "message": "All memes deleted"})
    except Exception as e:
        return jsonify({"error": "Failed to delete memes", "details": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))  # Default to 8080 if PORT is not set
    app.run(host="0.0.0.0", port=port)
