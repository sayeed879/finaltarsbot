import asyncpg
import logging
import math
from typing import List, Tuple, Optional
from dataclasses import dataclass

# We define a simple dataclass for the PDF results
@dataclass
class PdfResult:
    pdf_id: int
    title: str
    is_free: bool
    rank: float = 0.0  # Add rank with default value

async def search_pdfs(
    pool: asyncpg.Pool,
    user_class: str,
    is_premium: bool,
    query: str,
    page: int = 1,
    page_size: int = 5  # Show 5 results per page
) -> Tuple[List[PdfResult], int]:
    """
    Searches the database for PDFs.
    Returns a list of results and the total number of pages.
    """
    offset = (page - 1) * page_size
    
    # Use plainto_tsquery for more forgiving searches
    search_query_vector = f"plainto_tsquery('simple', $2)"

    # --- This is the SQL query for ranking and sorting ---
    # 1. It calculates a 'rank' based on how well the keywords match.
    # 2. It sorts:
    #    - If premium: Puts paid files (is_free=False) first, THEN by rank.
    #    - If free: Just sorts by rank.
    
    query_sql = f"""
        SELECT 
            pdf_id, 
            title, 
            is_free,
            ts_rank(to_tsvector('simple', COALESCE(search_keywords, title)), {search_query_vector}) as rank
        FROM pdfs
        WHERE 
            class_tag = $1 AND 
            (to_tsvector('simple', COALESCE(search_keywords, title)) @@ {search_query_vector}
             OR title ILIKE $2 || '%')
        ORDER BY
            CASE WHEN $3::BOOLEAN THEN is_free END ASC, -- Premium user sort
            rank DESC
        LIMIT $4 OFFSET $5;
    """
    
    # --- This query just gets the total count for pagination ---
    count_sql = f"""
        SELECT COUNT(*) 
        FROM pdfs
        WHERE 
            class_tag = $1 AND 
            (to_tsvector('simple', COALESCE(search_keywords, title)) @@ {search_query_vector}
             OR title ILIKE $2 || '%');
    """

    async with pool.acquire() as conn:
        try:
            # Run both queries
            total_rows_result = await conn.fetchrow(count_sql, user_class, query)
            total_rows = total_rows_result[0]
            
            if total_rows == 0:
                return [], 0

            search_results = await conn.fetch(
                query_sql, 
                user_class, 
                query, 
                is_premium, 
                page_size, 
                offset
            )
            
            # Convert results to our dataclass
            results_list = [PdfResult(**dict(row)) for row in search_results]
            
            # Calculate total pages
            total_pages = math.ceil(total_rows / page_size)
            
            return results_list, total_pages
            
        except Exception as e:
            logging.error(f"Error during PDF search: {e}")
            return [], 0

async def get_pdf_link_by_id(pool: asyncpg.Pool, pdf_id: int) -> Optional[str]:
    """
    Gets a single PDF's drive_link by its ID.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT drive_link FROM pdfs WHERE pdf_id = $1", pdf_id)
        return row['drive_link'] if row else None
    # (Add these at the end of the file)

async def admin_search_pdfs_by_title(pool: asyncpg.Pool, query: str) -> List[Tuple[int, str]]:
    """
    Admin-only search to find PDFs by title for deletion.
    Returns a list of (pdf_id, title) tuples.
    """
    # websearch_to_tsquery is good, but for admin, let's use simple matching
    search_term = f"%{query}%"
    
    async with pool.acquire() as conn:
        try:
            # We use ILIKE for case-insensitive matching
            results = await conn.fetch(
                """
                SELECT pdf_id, title FROM pdfs 
                WHERE title ILIKE $1 
                LIMIT 20
                """,
                search_term
            )
            return [(row['pdf_id'], row['title']) for row in results]
        except Exception as e:
            logging.error(f"Admin PDF search error: {e}")
            return []

async def delete_pdf_by_id(pool: asyncpg.Pool, pdf_id: int) -> bool:
    """
    Permanently deletes a PDF from the database using its ID.
    """
    async with pool.acquire() as conn:
        try:
            result = await conn.execute("DELETE FROM pdfs WHERE pdf_id = $1", pdf_id)
            if result == "DELETE 1":
                logging.info(f"Admin deleted PDF with ID: {pdf_id}")
                return True
            return False
        except Exception as e:
            logging.error(f"Error deleting PDF {pdf_id}: {e}")
            return False