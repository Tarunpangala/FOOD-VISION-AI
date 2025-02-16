# app.py
import os
import sqlite3
import streamlit as st
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from PIL import Image
import io

# Load environment variables
load_dotenv()

# Configure API keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

if not GEMINI_API_KEY:
    st.error("Gemini API key not found. Please add it to your .env file.")
    st.stop()

if not YOUTUBE_API_KEY:
    st.error("YouTube API key not found. Please add it to your .env file.")
    st.stop()

# Configure Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")
vision_model = genai.GenerativeModel("gemini-1.5-pro")

class IndianRecipeSystem:
    def __init__(self):
        """Initialize the Indian recipe system."""
        self.conn = sqlite3.connect("indian_recipes.db", check_same_thread=False)
        self.create_recipes_table()
        
        self.youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        
        # Indian cuisine regions
        self.cuisine_regions = [
            "Any",
            "Andhra",
            "Telangana",
            "South Indian",
            "North Indian",
            "Bengali",
            "Gujarati",
            "Maharashtrian",
            "Rajasthani",
            "Punjab"
        ]

    def create_recipes_table(self):
        """Create the database table for storing Indian recipes."""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS saved_recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_name TEXT NOT NULL,
                recipe_name_telugu TEXT,
                region TEXT NOT NULL,
                ingredients TEXT NOT NULL,
                instructions TEXT NOT NULL,
                video_link TEXT,
                created_date TEXT NOT NULL
            )
        ''')
        self.conn.commit()

    def identify_ingredients_from_image(self, uploaded_file):
        """Use Gemini Vision to identify Indian ingredients in the uploaded image."""
        try:
            image = Image.open(uploaded_file)
            
            prompt = """
            Analyze this image and identify Indian ingredients including:
            1. All visible food items, spices, and ingredients
            2. Approximate quantities if visible
            3. Condition (e.g., fresh, dried, powdered)
            4. Any visible packaging or storage containers
            
            Pay special attention to Indian spices, lentils, rice varieties, and fresh ingredients.
            Format as a comma-separated list with details in parentheses.
            Example: haldi powder (2 tbsp), fresh curry leaves (1 bunch), basmati rice (1 cup)
            
            Add any common Indian ingredients that might pair well with the visible ingredients.
            """
            
            response = vision_model.generate_content([
                prompt,
                {"mime_type": "image/jpeg", "data": uploaded_file.getvalue()}
            ])
            
            ingredients_list = [item.strip() for item in response.text.strip().split(',')]
            return ingredients_list
        
        except Exception as e:
            st.error(f"Error identifying ingredients: {str(e)}")
            return []

    def search_telugu_recipe_video(self, recipe_name, region):
        """Search YouTube for a Telugu recipe video."""
        try:
            # Create search query in both English and Telugu
            search_query = f"{recipe_name} {region} recipe in telugu vantalu తెలుగు వంటలు"
            
            request = self.youtube.search().list(
                part="snippet",
                q=search_query,
                type="video",
                maxResults=1,
                relevanceLanguage="te",  # Telugu language preference
                regionCode="IN"  # India region
            )
            response = request.execute()
            
            if response['items']:
                video_id = response['items'][0]['id']['videoId']
                return f"https://www.youtube.com/watch?v={video_id}"
            return None
            
        except HttpError as e:
            st.error(f"Error searching YouTube: {str(e)}")
            return None

    def generate_recipe(self):
        """Main function to generate Indian recipes from uploaded images."""
        st.title("🍲 Indian Recipe Generator")
        
        # Image upload section
        st.subheader("Upload a photo of your ingredients")
        uploaded_file = st.file_uploader("Choose an image...", type=["jpg", "jpeg", "png"])
        
        identified_ingredients = []
        if uploaded_file is not None:
            image = Image.open(uploaded_file)
            st.image(image, caption="Uploaded Ingredients", use_column_width=True)
            
            with st.spinner("Analyzing your ingredients..."):
                identified_ingredients = self.identify_ingredients_from_image(uploaded_file)
                
            if identified_ingredients:
                st.success("Identified ingredients:")
                for ingredient in identified_ingredients:
                    st.write(f"• {ingredient}")
            else:
                st.warning("No ingredients identified. Please try another image with clearer food items.")
        
        # Recipe preferences
        region = st.selectbox(
            "Select Region/Cuisine",
            self.cuisine_regions
        )
        
        spice_level = st.slider("Spice Level", 1, 5, 3)
        
        meal_type = st.selectbox(
            "Type of Dish",
            ["Any", "Curry", "Rice Dish", "Breakfast", "Snack", "Sweet", "Chutney", "Roti/Bread"]
        )
        
        cooking_time = st.slider("Maximum cooking time (minutes)", 5, 120, 30, step=5)
        
        if st.button("Generate Recipe") and identified_ingredients:
            prompt = f"""
            Create a detailed {region} Indian recipe using these ingredients: {', '.join(identified_ingredients)}.
            
            Region: {region if region != "Any" else "Indian"}
            Spice Level: {spice_level}/5
            Type of Dish: {meal_type if meal_type != "Any" else "Any"}
            Maximum cooking time: {cooking_time} minutes

            Format your response as follows:
            
            # [RECIPE NAME IN ENGLISH]
            # [RECIPE NAME IN TELUGU]
            
            ## Ingredients
            - [List all ingredients with measurements]
            
            ## Instructions
            1. [Step-by-step cooking instructions]
            2. [...]
            
            ## Tips
            - [1-3 cooking tips specific to Indian cuisine]
            
            ## Serving Suggestions
            - [What to serve this dish with]
            
            Important: Use the identified ingredients and suggest common Indian substitutes if needed.
            Include traditional cooking methods and authentic spicing.
            """
            
            with st.spinner("Creating your Indian recipe..."):
                result = self.safe_generate_content(prompt)
                if result:
                    st.markdown(result)
                    
                    # Extract recipe names
                    recipe_lines = result.split('\n')[:2]
                    recipe_name_en = recipe_lines[0].replace('#', '').strip()
                    recipe_name_te = recipe_lines[1].replace('#', '').strip()
                    
                    with st.spinner("Finding a Telugu video tutorial..."):
                        video_link = self.search_telugu_recipe_video(recipe_name_en, region)
                        
                    if video_link:
                        st.subheader("వంటకం వీడియో / Recipe Video")
                        st.video(video_link)
                    
                    if st.button("Save Recipe"):
                        try:
                            ingredients_text = ', '.join(identified_ingredients)
                            
                            cursor = self.conn.cursor()
                            cursor.execute('''
                                INSERT INTO saved_recipes 
                                (recipe_name, recipe_name_telugu, region, ingredients, 
                                instructions, video_link, created_date)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            ''', (recipe_name_en, recipe_name_te, region, ingredients_text, 
                                  result, video_link, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                            self.conn.commit()
                            
                            st.success("Recipe saved successfully!")
                            st.balloons()
                                
                        except Exception as e:
                            st.error(f"Error saving recipe: {e}")
        
        elif not identified_ingredients and st.button("Generate Recipe"):
            st.warning("Please upload a photo of your ingredients first")

    def view_saved_recipes(self):
        """Display and manage saved Indian recipes."""
        st.title("📚 My Saved Recipes")

        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, recipe_name, recipe_name_telugu, region, ingredients, created_date  
            FROM saved_recipes
            ORDER BY created_date DESC
        """)
        recipes = cursor.fetchall()

        if recipes:
            for recipe in recipes:
                recipe_id, recipe_name, recipe_name_te, region, ingredients, created_date = recipe
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    with col1:
                        st.write(f"**{recipe_name}**")
                        st.write(f"*{recipe_name_te}*")
                    with col2:
                        st.write(f"Region: {region}")
                        st.write(f"Ingredients: {ingredients}")
                    with col3:
                        if st.button("View", key=f"view_{recipe_id}"):
                            self.view_recipe_details(recipe_id)
                        if st.button("Delete", key=f"del_{recipe_id}"):
                            self.delete_recipe(recipe_id)
                            st.rerun()
                st.divider()
        else:
            st.info("No saved recipes yet. Upload ingredients and generate recipes to get started!")

    def view_recipe_details(self, recipe_id):
        """Display detailed view of a specific Indian recipe."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT recipe_name, recipe_name_telugu, instructions, video_link 
            FROM saved_recipes WHERE id = ?
        ''', (recipe_id,))
        recipe = cursor.fetchone()
        
        if recipe:
            recipe_name, recipe_name_te, instructions, video_link = recipe
            st.subheader(f"{recipe_name} / {recipe_name_te}")
            st.markdown(instructions)
            
            if video_link:
                st.subheader("వంటకం వీడియో / Recipe Video")
                st.video(video_link)
        else:
            st.error("Recipe not found!")

    def delete_recipe(self, recipe_id):
        """Delete a recipe from the database."""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM saved_recipes WHERE id = ?', (recipe_id,))
        self.conn.commit()
        st.success("Recipe deleted!")
        st.balloons()

    def safe_generate_content(self, prompt):
        """Safely generate content using Gemini AI."""
        try:
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            st.error(f"Error generating content: {e}")
            return None

def main():
    """Main application entry point."""
    st.set_page_config(
        page_title="Indian Recipe Generator",
        page_icon="🍲",
        layout="wide"
    )

    system = IndianRecipeSystem()

    st.sidebar.title("🍲 Indian Recipe Generator")
    options = ["Home", "Generate Recipe", "Saved Recipes"]
    choice = st.sidebar.selectbox("Navigate", options)

    if choice == "Generate Recipe":
        system.generate_recipe()
    elif choice == "Saved Recipes":
        system.view_saved_recipes()
    else:
        st.title("Welcome to the Indian Recipe Generator! 🍲")
        st.markdown("""
        ### Turn Your Ingredients Into Delicious Indian Dishes!
        
        This system helps you:
        - 📸 Upload photos of your ingredients for automatic identification
        - 🍛 Get personalized Indian recipes based on your available ingredients
        - 🎥 Watch Telugu video tutorials for your recipes
        - 📚 Save your favorite recipes for later
        
        Get started by uploading a photo of your ingredients!
        """)

        try:
            cursor = system.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM saved_recipes")
            count = cursor.fetchone()[0]
            if count > 0:
                st.success(f"You have saved {count} recipes so far!")
        except:
            pass

if __name__ == "__main__":
    main()