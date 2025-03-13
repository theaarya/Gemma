import csv
import numpy as np
import solr

# --- Configuration ---
SOLR_URL = 'http://localhost:8983/solr/diamond_core'  # Replace with your Solr URL and core name
CSV_FILE = 'diamond.csv'  # Replace with your CSV file path
NPY_FILE = 'diamond_embeddings.npy'  # Replace with your NPY file path

# --- Solr Connection ---
solr_conn = solr.Solr(SOLR_URL)

# --- Load Data ---
csv_data = []
with open(CSV_FILE, 'r', encoding='utf-8') as file:  # Ensure correct encoding if needed
    csv_reader = csv.DictReader(file)
    for row in csv_reader:
        csv_data.append(row)

npy_vectors = np.load(NPY_FILE)

# --- Data Validation ---
if len(csv_data) != len(npy_vectors):
    raise ValueError("Number of rows in CSV does not match number of vectors in NPY file.")
if npy_vectors.shape[1] != 384:  # Assuming vectors are in rows, check 2nd dimension for vector length
    raise ValueError(f"NPY vectors dimension is {npy_vectors.shape[1]}, but schema expects 384.")


# --- Update Solr Documents with video, image, and pdf ---

for i in range(1100000, 1113000):
    csv_row = csv_data[i]
    vector = npy_vectors[i]

    # **Crucial: Map CSV columns to Solr fields based on your schema and CSV header**
    solr_doc = {
        'id': csv_row.get('id') or str(i),  # Assuming 'id' column in CSV, or generate ID if not. **REQUIRED for updates**
        'Carat': csv_row.get('Carat'),  # Map CSV column 'Carat' to Solr field 'Carat'
        'Clarity': csv_row.get('Clarity'),  # Map CSV column 'Clarity' to Solr field 'Clarity'
        'Color': csv_row.get('Color'),  # ... and so on for other CSV columns ...
        'Cut': csv_row.get('Cut'),
        'Depth': csv_row.get('Depth'),
        'Flo': csv_row.get('Flo'),
        'Height': csv_row.get('Height'),
        'Lab': csv_row.get('Lab'),
        'Length': csv_row.get('Length'),
        'Polish': csv_row.get('Polish'),
        'Price': csv_row.get('Price'),
        'Shape': csv_row.get('Shape'),
        'Style': csv_row.get('Style'),
        'Symmetry': csv_row.get('Symmetry'),
        'Width': csv_row.get('Width'),
        'video': csv_row.get('video'),  # Add video field from CSV
        'image': csv_row.get('image'),  # Add image field from CSV
        'pdf': csv_row.get('pdf'),  # Add pdf field from CSV
        'vector': vector.tolist()  # **Map NPY vector to the 'vector' field. Convert numpy array to Python list**
    }

    try:
        solr_conn.add(solr_doc)  # Upload one document at a time - this will update if document with same ID exists
        print(f"Updated document {i+1}")  # Optional: Print progress after each document upload
    except Exception as e:
        print(f"Error updating document {i+1}: {e}")
        # Consider adding error handling logic here (e.g., logging, skipping, etc.)

# --- Commit Changes ---
solr_conn.commit()
print("Commit complete. Data updated in Solr with video, image, and pdf fields.")