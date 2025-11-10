# (in importer.py)
import asyncio
import csv
import asyncpg
import os
import logging
from dotenv import load_dotenv

# --- Setup ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - IMPORTER - %(message)s")
load_dotenv()
logging.info("Loaded .env file (if present).")

# --- THIS IS THE FIXED PART ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logging.critical("CRITICAL: DATABASE_URL is NOT SET in your Railway variables! Can't run importer.")
    exit(1)

CSV_FILE_PATH = 'pdfs.csv'
# --- END OF FIXED PART ---

# (The rest of the file stays the same)
...
# --- END OF FIXED PART ---


async def bulk_insert_pdfs():
    """
    Connects to the database, reads the CSV, and bulk-inserts all PDFs.
    """
    conn = None
    try:
        # Connect to your PostgreSQL database
        conn = await asyncpg.connect(DATABASE_URL)
        logging.info("✅ Database connection successful.")

        # Prepare a list to hold all our PDF data
        pdf_records_to_insert = []
        
        # Open and read the CSV file
        try:
            with open(CSV_FILE_PATH, mode='r', encoding='utf-8') as file:
                csv_reader = csv.DictReader(file)
                for i, row in enumerate(csv_reader):
                    try:
                        is_free_bool = row['is_free'].lower().strip() == 'yes'
                        pdf_records_to_insert.append(
                            (
                                row['title'],
                                row['drive_link'],
                                row['class_tag'],
                                is_free_bool,
                                row['search_keywords']
                            )
                        )
                    except KeyError as e:
                        logging.error(f"Missing column in CSV on row {i+1}: {e}. Skipping row.")
                    except Exception as e:
                        logging.error(f"Error processing row {i+1}: {e}. Row data: {row}")

        except FileNotFoundError:
            logging.critical(f"❌ ERROR: The file '{CSV_FILE_PATH}' was not found.")
            return

        if not pdf_records_to_insert:
            logging.warning("⚠️ No valid records found in CSV file. Exiting.")
            return

        logging.info(f"Found {len(pdf_records_to_insert)} records in {CSV_FILE_PATH}.")
        logging.info("Starting bulk insert...")

        insert_query = """
        INSERT INTO pdfs (title, drive_link, class_tag, is_free, search_keywords)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (pdf_id) DO NOTHING;
        """
        await conn.executemany(insert_query, pdf_records_to_insert)
        
        logging.info(f"✅ Success! Successfully imported {len(pdf_records_to_insert)} PDFs into the database.")

        # --- ADD/VERIFY AI PROMPTS ---
        logging.info("Adding/Verifying class AI prompts...")
        try:
            prompts_to_add = [
                ('default', 'You are a helpful assistant. Keep all your responses concise and to the point.you are TARS developed by sayeed .'),
                ('10th', 'You are a helpful AI assistant for a 10th-grade student in India. Keep all your responses concise and to the point.you are TARS developed by sayeed.'),
                ('11th', 'You are an expert AI tutor for an 11th-grade PCMB student. Keep all your responses concise and to the point.you are TARS developed by sayeed.'),
                ('12th', 'You are an advanced AI assistant for a 12th-grade student. Keep all your responses concise and to the point. you are TARS developed by sayeed.'),
                ('jee', 'You are a high-level JEE exam expert. Your answers must be technical and precise. Keep all your responses concise and to the point.you are TARS developed by sayeed.'),
                ('neet', 'You are a medical entrance exam expert (NEET). Focus on biology and chemistry. Keep all your responses concise and to the point.you are TARS developed by sayeed.')
            ]
            
            prompt_query = """
            INSERT INTO ai_prompts (class_tag, system_prompt)
            VALUES ($1, $2)
            ON CONFLICT (class_tag) DO UPDATE SET system_prompt = $2;
            """
            
            await conn.executemany(prompt_query, prompts_to_add)
            logging.info(f"✅ Successfully added/updated {len(prompts_to_add)} AI prompts.")
            
        except Exception as e:
            logging.error(f"❌ Error adding AI prompts: {e}")

    except asyncpg.exceptions.UndefinedTableError:
        logging.critical("❌ ERROR: The table 'pdfs' or 'ai_prompts' does not exist.")
    except Exception as e:
        logging.critical(f"❌ An unexpected error occurred: {e}")
    finally:
        if conn:
            await conn.close()
            logging.info("Database connection closed.")

if __name__ == "__main__":
    asyncio.run(bulk_insert_pdfs())