import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss
import re
import os
from groq import Groq
from dotenv import load_dotenv

# Global: Path for embeddings (used in temporary index building)
EMBEDDING_FILE_PATH = 'diamond_embeddings.npy'

# ------------------- Data Preparation & Embedding Generation -------------------
def data_and_embedding(file_path, embedding_file, faiss_index_file, dataframe_file, model_path):
    df = pd.read_csv(file_path)
    df = df.replace({r'[^\x00-\x7F]+': ''}, regex=True)
    # Convert all data values to lowercase
    df = df.apply(lambda x: x.astype(str).str.lower())

    print(f"Number of rows in dataset: {df.shape[0]}")
    print(f"Column names in dataset: {df.columns.tolist()}")  # Print column names

    # Create a combined text field that includes Style
    df['combined_text'] = (
        "Style: " + df['Style'].astype(str) + ", " +
        "Carat: " + df['Carat'].astype(str) + ", " +
        "Clarity: " + df['Clarity'].astype(str) + ", " +
        "Color: " + df['Color'].astype(str) + ", " +
        "Cut: " + df['Cut'].astype(str) + ", " +
        "Shape: " + df['Shape'].astype(str) + ", " +
        "Price: " + df['Price'].astype(str) + ", " +
        "Lab: " + df['Lab'].astype(str) + ", " +
        "Polish: " + df['Polish'].astype(str) + ", " +
        "Symmetry: " + df['Symmetry'].astype(str)
    )

    # Ensure Carat is numeric
    df["Carat"] = pd.to_numeric(df["Carat"], errors="coerce")

    print("First combined text:", df['combined_text'].iloc[0])

    # Generate embeddings using SentenceTransformer
    model = SentenceTransformer('all-mpnet-base-v2')
    embeddings = model.encode(df['combined_text'].tolist(), convert_to_numpy=True)
    print(f"Shape of embeddings: {embeddings.shape}")

    # Build FAISS index using L2 distance
    embedding_dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(embedding_dimension)
    index.add(embeddings)

    # Save embeddings, FAISS index, and dataframe to disk
    np.save(embedding_file, embeddings)
    faiss.write_index(index, faiss_index_file)
    df.to_csv(dataframe_file, index=False)
    model.save(model_path)

    print("Model, embeddings, and FAISS index saved to disk.")
    return df, embeddings, index, model

# ------------------- Load Data & FAISS Index -------------------
def load_data_and_index(embedding_file, faiss_index_file, dataframe_file, model_path):
    df = pd.read_csv(dataframe_file)
    print(f"Column names in loaded dataset: {df.columns.tolist()}")  # Print column names
    df["Carat"] = pd.to_numeric(df["Carat"], errors="coerce")
    embeddings = np.load(embedding_file)
    index = faiss.read_index(faiss_index_file)
    model = SentenceTransformer(model_path)
    print("Loaded data, embeddings, FAISS index, and model from disk.")
    return df, embeddings, index, model

# ------------------- Utility: Extract Constraints from Query -------------------
def extract_constraints_from_query(user_query):
    """
    Extracts constraints (Carat, Color, Clarity, Cut, Symmetry, Polish, Style, Shape, Budget)
    from the user's query. Non-numeric values are normalized to lowercase.
    Returns a dictionary.
    """
    constraints = {}

    # Extract style (e.g., "lab grown", "lab", or "natural")
    style_match = re.search(r'\b(lab\s*grown|lab|natural)\b', user_query, re.IGNORECASE)
    if style_match:
        style = style_match.group(1).lower()
        # Normalize "lab" or "lab grown" to "labgrown"
        if "lab" in style:
            constraints["Style"] = "labgrown"
        else:
            constraints["Style"] = "natural"

    # Extract Carat (e.g., "0.8 carat")
    carat_match = re.search(r'(\d+(\.\d+)?)\s*-?\s*carat', user_query, re.IGNORECASE)
    if carat_match:
        constraints["Carat"] = float(carat_match.group(1))

    # Extract Budget (e.g., "under price 2000" or "at price 2000")
    budget_match = re.search(r'\b(?:under|at price|price)\s*\$?(\d+(?:,\d+)?)\b', user_query, re.IGNORECASE)
    if budget_match:
        budget_str = budget_match.group(1).replace(',', '')
        constraints["Budget"] = float(budget_str)

    # Extract Color (e.g., "E", "G") – normalized to lowercase
    color_match = re.search(r'\b([a-j])\b', user_query, re.IGNORECASE)
    if color_match:
        constraints["Color"] = color_match.group(1).lower()

    # Extract Clarity (e.g., "VS1", "VVS2", etc.) – normalized to lowercase
    clarity_match = re.search(r'\b(if|vvs1|vvs2|vs1|vs2|si1|si2)\b', user_query, re.IGNORECASE)
    if clarity_match:
        constraints["Clarity"] = clarity_match.group(1).lower()

    # Extract Cut: match either "cut is excellent" or "excellent cut"
    cut_match = re.search(r'(?:cut\s*(?:is\s*)?(excellent|ideal|very good|good))|(?:(excellent|ideal|very good|good)\s*cut)', user_query, re.IGNORECASE)
    if cut_match:
        quality = cut_match.group(1) if cut_match.group(1) is not None else cut_match.group(2)
        constraints["Cut"] = quality.lower()

    # Extract Polish: match either "polish is very good" or "very good polish"
    polish_match = re.search(r'(?:polish\s*(?:is\s*)?(excellent|ideal|very good|good))|(?:(excellent|ideal|very good|good)\s*polish)', user_query, re.IGNORECASE)
    if polish_match:
        quality = polish_match.group(1) if polish_match.group(1) is not None else polish_match.group(2)
        constraints["Polish"] = quality.lower()

    # Extract Symmetry: match either "symmetry is good" or "good symmetry"
    symmetry_match = re.search(r'(?:symmetry\s*(?:is\s*)?(excellent|ideal|very good|good))|(?:(excellent|ideal|very good|good)\s*symmetry)', user_query, re.IGNORECASE)
    if symmetry_match:
        quality = symmetry_match.group(1) if symmetry_match.group(1) is not None else symmetry_match.group(2)
        constraints["Symmetry"] = quality.lower()

    # Extract Shape (e.g., "round", "princess", etc.) – normalized to lowercase
    shape_match = re.search(r'\b(round|princess|emerald|asscher|cushion|marquise|radiant|oval|pear|heart|square radiant)\b', user_query, re.IGNORECASE)
    if shape_match:
        constraints["Shape"] = shape_match.group(1).lower()

    # Optional: Extract price ordering preferences if no explicit budget is provided
    lower_query = user_query.lower()
    if "Budget" not in constraints:
        if any(keyword in lower_query for keyword in ["cheapest", "lowest price", "affordable", "low budget"]):
            constraints["PriceOrder"] = "asc"
        elif any(keyword in lower_query for keyword in ["most expensive", "highest price", "priciest", "expensive", "high budget"]):
            constraints["PriceOrder"] = "desc"

    return constraints

# ------------------- Hybrid Search (Semantic + Filter + Composite Ranking) -------------------
def hybrid_search(user_query, df, faiss_index, model, top_k=200):
    """
    1. Extract constraints from the query.
    2. Filter the DataFrame based on style, shape, clarity, budget, and quality attributes.
    3. If Carat is specified, pre-filter for near-exact matches using a tolerance and perform a FAISS search.
    4. Compute a composite score (if needed) and return the top 5 results.
    """
    constraints = extract_constraints_from_query(user_query)

    # Restrict by Style if specified
    if "Style" in constraints:
        style_val = constraints["Style"].lower()
        df = df[df['Style'].str.lower().str.contains(style_val)]
        if df.empty:
            print("No diamonds found for the specified style.")
            return pd.DataFrame()
        
    # Restrict by Shape if specified
    if "Shape" in constraints:
        df = df[df["Shape"].str.lower().str.contains(constraints["Shape"].lower())]
        if df.empty:
            print(f"No {constraints['Shape']} diamonds found.")
            return pd.DataFrame()
        
    # Filter by Clarity if specified (exact match)
    if "Clarity" in constraints:
        clarity_regex = rf'^{re.escape(constraints["Clarity"].lower())}$'
        df = df[df["Clarity"].str.lower().str.match(clarity_regex)]
        if df.empty:
            print(f"No diamonds found with clarity {constraints['Clarity']}.")
            return pd.DataFrame()

    # If Budget is specified, filter for diamonds under that price
    if "Budget" in constraints:
        user_budget = constraints["Budget"]
        df = df[df["Price"] <= user_budget]
        if df.empty:
            print(f"No diamonds found under price {user_budget}.")
            return pd.DataFrame()
        
    # Strict filtering for quality attributes if 2 or more are specified
    quality_attrs = ["Cut", "Polish", "Symmetry"]
    specified_quality = [attr for attr in quality_attrs if attr in constraints]
    if len(specified_quality) >= 2:
        for attr in specified_quality:
            df = df[df[attr].str.lower() == constraints[attr].lower()]
        if df.empty:
            print(f"No diamonds found that exactly match the specified {', '.join(specified_quality)} criteria.")
            return pd.DataFrame()

    # If Carat is not specified, use fallback sorting:
    if "Carat" not in constraints:
        if any(word in user_query.lower() for word in ["minimum", "lowest", "smallest"]):
            results_df = df.sort_values(by="Carat", ascending=True)
        else:
            results_df = df.sort_values(by="Price", ascending=False)
        return results_df.head(5).reset_index(drop=True)

    # If Carat is specified, set tolerance based on style
    tolerance = 0.01 if constraints.get("Style", "").lower() == "labgrown" else 0.05
    df_carat = df[
        (df['Carat'] >= constraints["Carat"] - tolerance) &
        (df['Carat'] <= constraints["Carat"] + tolerance)
    ]
    if df_carat.empty:
        relaxed_tolerance = tolerance * 2
        df_carat = df[
            (df['Carat'] >= constraints["Carat"] - relaxed_tolerance) &
            (df['Carat'] <= constraints["Carat"] + relaxed_tolerance)
        ]
    if not df_carat.empty:
        subset_indices = df_carat.index.tolist()
        all_embeddings = np.load(EMBEDDING_FILE_PATH)
        subset_embeddings = all_embeddings[subset_indices]
        temp_index = faiss.IndexFlatL2(all_embeddings.shape[1])
        temp_index.add(subset_embeddings)
        new_top_k = min(top_k, len(df_carat))
        query_embedding = model.encode(user_query, convert_to_numpy=True)
        D, I = temp_index.search(np.array([query_embedding]), new_top_k)
        valid_indices = [i for i in I[0] if 0 <= i < len(df_carat)]
        valid_D = D[0][:len(valid_indices)]
        results_df = df_carat.iloc[valid_indices].copy()
        results_df['distance'] = valid_D
    else:
        query_embedding = model.encode(user_query, convert_to_numpy=True)
        new_top_k = min(top_k, df.shape[0])
        D, I = faiss_index.search(np.array([query_embedding]), new_top_k)
        valid_indices = [i for i in I[0] if 0 <= i < df.shape[0]]
        valid_D = D[0][:len(valid_indices)]
        results_df = df.iloc[valid_indices].copy()
        results_df['distance'] = valid_D

    # Global Price Ordering Block: Check for explicit price keywords or extracted PriceOrder.
    if any(word in user_query.lower() for word in ["cheapest", "lowest price", "affordable", "low budget"]) or ("PriceOrder" in constraints and constraints["PriceOrder"] == "asc"):
        results_df = results_df.sort_values(by='Price', ascending=True)
        return results_df.head(5).reset_index(drop=True)
    elif any(word in user_query.lower() for word in ["most expensive", "highest price", "priciest", "expensive", "high budget"]) or ("PriceOrder" in constraints and constraints["PriceOrder"] == "desc"):
        results_df = results_df.sort_values(by='Price', ascending=False)
        return results_df.head(5).reset_index(drop=True)

    # Additional sorting for Carat if query mentions "highest", "largest", "maximum"
    if any(word in user_query.lower() for word in ["highest", "largest", "maximum"]):
        results_df = results_df.sort_values(by='Carat', ascending=False)
        return results_df.head(5).reset_index(drop=True)
    # Or if query mentions "minimum", "lowest", "smallest"
    elif any(word in user_query.lower() for word in ["minimum", "lowest", "smallest"]):
        results_df = results_df.sort_values(by='Carat', ascending=True)
        return results_df.head(5).reset_index(drop=True)
    else:
        # Composite ranking if no explicit ordering keywords are detected
        def compute_score(row, constraints, df_filtered):
            score = row['distance']
            if "Carat" in constraints:
                score += 1000 * abs(row["Carat"] - constraints["Carat"])
            else:
                median_carat = df_filtered['Carat'].median()
                score += 100 * abs(row["Carat"] - median_carat)
            if "Budget" in constraints:
                user_budget = constraints["Budget"]
                score += 0.05 * abs(row["Price"] - user_budget)
            else:
                try:
                    price = float(row["Price"])
                except:
                    price = 0
                score += 0.1 * price
            for attr, penalty in [("Clarity", 50), ("Color", 50)]:
                if attr in constraints and row[attr].lower() != constraints[attr].lower():
                    score += penalty
            for attr, penalty in [("Cut", 20), ("Symmetry", 20), ("Polish", 20)]:
                if attr in constraints and row[attr].lower() != constraints[attr].lower():
                    score += penalty
            return score

        results_df['score'] = results_df.apply(lambda row: compute_score(row, constraints, df), axis=1)
        results_df = results_df.sort_values(by='score', ascending=True)
        return results_df.head(5).reset_index(drop=True)

# ------------------- Groq Integration -------------------
def generate_groq_response(user_query, relevant_data, client):
    prompt = f"""
You are a friendly and knowledgeable shop assistant at a diamond store.
Your goal is to help the customer find diamonds that best match their query.

First, write a brief introduction responding to the user's query, explaining what you found.
Then, return a structured JSON array of the top diamonds that match their criteria.

Here's the specific format to use:
1. A brief introduction paragraph, one or two sentences.
2. A special marker <diamond-data> followed by a valid JSON array of diamond objects.
3. Close with </diamond-data>

Example format:
"I found several diamonds matching your criteria. Here are the best options:
<diamond-data>
[
  {{
    "Carat": 1.01,
    "Clarity": "VS1",
    "Color": "F",
    "Cut": "Excellent",
    "Shape": "Round",
    "Price": "5000",
    "Style": "Natural",
    "Polish": "Excellent",
    "Symmetry": "Excellent"
  }},
  ...more diamonds...
]
</diamond-data>"

Below are some diamond details that might be relevant:
{relevant_data}

Parse this data and create a proper JSON response as described above.
Ensure the JSON is valid and can be parsed by JavaScript's JSON.parse() function.
"""
    chat_completion = client.chat.completions.create(
        messages=[{"role": "system", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.7,
        max_tokens=750
    )
    return chat_completion.choices[0].message.content

# ------------------- Main Chatbot Logic -------------------
def diamond_chatbot(user_query, df, faiss_index, model, client):
    """
    Handles the chatbot's logic and returns the chatbot's response as a string.
    """
    # Handle greetings
    if user_query.strip().lower() in ["hi", "hello"]:
        return "Hey there! I'm your diamond guru 😎. Ready to help you find that perfect sparkle? Tell me what you're looking for!"

    # Extract constraints from the user query
    constraints = extract_constraints_from_query(user_query)
    
    # Only fall back if there are no constraints AND no ordering keywords in the query.
    if not constraints and not any(keyword in user_query.lower() for keyword in ["maximum", "minimum", "lowest", "highest", "largest", "smallest"]):
        return "Hello! I'm your diamond assistant. Please let me know your preferred carat, clarity, color, cut, or budget so I can help you find the perfect diamond."

    # Proceed with searching for diamonds
    results_df = hybrid_search(user_query, df, faiss_index, model, top_k=200)
    if results_df.empty:
        return "No matching diamonds found. Please try a different query."

    # Select top 5 matching diamonds
    top_5 = results_df.head(5)
    relevant_data = "\n".join(top_5['combined_text'].tolist())

    # Generate response using Groq AI
    groq_response = generate_groq_response(user_query, relevant_data, client)

    return groq_response



def convert_markdown_to_html(text):
    # Replace markdown bold (text) with HTML <strong>text</strong>
    return re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)

# ------------------- Main Execution -------------------
def main():
    load_dotenv()
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    client = Groq()
    embedding_file = 'diamond_embeddings.npy'
    faiss_index_file = 'diamond_faiss_index.faiss'
    dataframe_file = 'diamond_dataframe.csv'
    model_path = 'sentence_transformer_model'
    file_path = 'diamonds.csv'

    try:
        df, embeddings, index, model = load_data_and_index(embedding_file, faiss_index_file, dataframe_file, model_path)
        print("Data, embeddings, and FAISS index loaded from disk.")
    except Exception as e:
        print("Error loading existing data:", e)
        print("Running first-time data load and creating index...")
        df, embeddings, index, model = data_and_embedding(file_path, embedding_file, faiss_index_file, dataframe_file, model_path)
    
    # Conversation loop
    while True:
        user_query = input("Hi! How can I help you? : ")
        if user_query.lower() in ["exit", "quit"]:
            print("Thank you for visiting! Have a wonderful day.")
            break
        
        # Process greetings
        if user_query.strip().lower() in ["hi", "hello"]:
            response = diamond_chatbot(user_query, df, index, model, client)
            print(response)
            print("\n---\n")
            continue

        constraints = extract_constraints_from_query(user_query)
        if "Style" not in constraints:
            style_input = input("Please specify the style (LabGrown or Natural): ")
            user_query += " " + style_input
        
        response = diamond_chatbot(user_query, df, index, model, client)
        print(response)
        print("\n---\n")
    
if __name__ == "__main__":
    main()
