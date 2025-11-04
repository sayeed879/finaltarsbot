import asyncpg
import logging
import math
from typing import List, Tuple, Optional
from dataclasses import dataclass

# PDF result dataclass with enhanced fields
@dataclass
class PdfResult:
    pdf_id: int
    title: str
    is_free: bool
    rank: float = 0.0

async def search_pdfs(
    pool: asyncpg.Pool,
    user_class: str,
    is_premium: bool,
    query: str,
    page: int = 1,
    page_size: int = 5
) -> Tuple[List[PdfResult], int]:
    """
    Enhanced PDF search with better ranking and error handling.
    Returns a tuple of (results_list, total_pages).
    """
    offset = (page - 1) * page_size
    
    # Sanitize and prepare query
    search_term = query.strip()
    
    # Create search vectors for both exact and fuzzy matching
    # Use websearch_to_tsquery for better natural language handling
    search_query_vector = "websearch_to_tsquery('simple', $2)"
    
    # Enhanced SQL query with multiple search strategies
    query_sql = f"""
        WITH ranked_pdfs AS (
            SELECT 
                pdf_id, 
                title, 
                is_free,
                -- Multi-strategy ranking
                GREATEST(
                    -- Exact phrase match (highest priority)
                    CASE WHEN title ILIKE '%' || $2 || '%' THEN 100 ELSE 0 END,
                    -- Full-text search rank
                    ts_rank(
                        to_tsvector('simple', COALESCE(search_keywords, '') || ' ' || title),
                        {search_query_vector}
                    ) * 50,
                    -- Keyword starts with query (medium priority)
                    CASE WHEN title ILIKE $2 || '%' THEN 30 ELSE 0 END,
                    -- Contains all words (low priority)
                    CASE WHEN position(lower($2) in lower(title)) > 0 THEN 10 ELSE 0 END
                ) as rank
            FROM pdfs
            WHERE 
                class_tag = $1 AND 
                (
                    -- Full-text search
                    to_tsvector('simple', COALESCE(search_keywords, '') || ' ' || title) @@ {search_query_vector}
                    -- OR simple LIKE for partial matches
                    OR title ILIKE '%' || $2 || '%'
                    OR search_keywords ILIKE '%' || $2 || '%'
                )
        )
        SELECT pdf_id, title, is_free, rank
        FROM ranked_pdfs
        WHERE rank > 0
        ORDER BY
            -- Premium users see paid content first, then by rank
            CASE WHEN $3::BOOLEAN THEN is_free END ASC,
            rank DESC,
            title ASC
        LIMIT $4 OFFSET $5;
    """
    
    # Count query with same WHERE conditions
    count_sql = f"""
        SELECT COUNT(*) 
        FROM pdfs
        WHERE 
            class_tag = $1 AND 
            (
                to_tsvector('simple', COALESCE(search_keywords, '') || ' ' || title) @@ {search_query_vector}
                OR title ILIKE '%' || $2 || '%'
                OR search_keywords ILIKE '%' || $2 || '%'
            );
    """

    async with pool.acquire() as conn:
        try:
            # Get total count
            total_rows_result = await conn.fetchrow(count_sql, user_class, search_term)
            total_rows = total_rows_result[0] if total_rows_result else 0
            
            if total_rows == 0:
                logging.info(f"No PDFs found for query '{search_term}' in class '{user_class}'")
                return [], 0

            # Get paginated results
            search_results = await conn.fetch(
                query_sql, 
                user_class, 
                search_term, 
                is_premium, 
                page_size, 
                offset
            )
            
            # Convert results to dataclass
            results_list = [PdfResult(**dict(row)) for row in search_results]
            
            # Calculate total pages
            total_pages = math.ceil(total_rows / page_size)
            
            logging.info(
                f"PDF search: query='{search_term}', class='{user_class}', "
                f"premium={is_premium}, found={total_rows}, page={page}/{total_pages}"
            )
            
            return results_list, total_pages
            
        except Exception as e:
            logging.error(f"Error during PDF search: {e}")
            logging.error(f"Query: '{search_term}', Class: '{user_class}'")
            return [], 0

async def get_pdf_link_by_id(pool: asyncpg.Pool, pdf_id: int) -> Optional[str]:
    """
    Retrieves a PDF's download link by its ID.
    """
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT drive_link FROM pdfs WHERE pdf_id = $1", 
                pdf_id
            )
            
            if row:
                logging.info(f"Retrieved PDF link for ID {pdf_id}")
                return row['drive_link']
            else:
                logging.warning(f"PDF with ID {pdf_id} not found")
                return None
                
        except Exception as e:
            logging.error(f"Error retrieving PDF link for ID {pdf_id}: {e}")
            return None

async def admin_search_pdfs_by_title(pool: asyncpg.Pool, query: str) -> List[Tuple[int, str]]:
    """
    Admin-only search to find PDFs by title for deletion/management.
    Uses simple ILIKE matching for admin convenience.
    Returns a list of (pdf_id, title) tuples.
    """
    search_term = f"%{query}%"
    
    async with pool.acquire() as conn:
        try:
            results = await conn.fetch(
                """
                SELECT pdf_id, title, class_tag 
                FROM pdfs 
                WHERE title ILIKE $1 
                ORDER BY 
                    -- Exact matches first
                    CASE WHEN title ILIKE $2 THEN 0 ELSE 1 END,
                    title ASC
                LIMIT 20
                """,
                search_term,
                query  # For exact match check
            )
            
            # Include class tag in results for admin clarity
            result_list = [(row['pdf_id'], f"{row['title']} [{row['class_tag']}]") for row in results]
            
            logging.info(f"Admin search for '{query}': found {len(result_list)} results")
            return result_list
            
        except Exception as e:
            logging.error(f"Admin PDF search error: {e}")
            return []

async def delete_pdf_by_id(pool: asyncpg.Pool, pdf_id: int) -> bool:
    """
    Permanently deletes a PDF from the database using its ID.
    Returns True if successful, False otherwise.
    """
    async with pool.acquire() as conn:
        try:
            result = await conn.execute("DELETE FROM pdfs WHERE pdf_id = $1", pdf_id)
            
            # Check if exactly one row was deleted
            if result == "DELETE 1":
                logging.info(f"✅ Successfully deleted PDF with ID: {pdf_id}")
                return True
            else:
                logging.warning(f"PDF with ID {pdf_id} not found or already deleted")
                return False
                
        except Exception as e:
            logging.error(f"Error deleting PDF {pdf_id}: {e}")
            return False

# ============================================================================
# BULK OPERATIONS (for admin use)
# ============================================================================

async def bulk_add_pdfs(
    pool: asyncpg.Pool, 
    pdf_records: List[Tuple[str, str, str, bool, str]]
) -> int:
    """
    Bulk insert multiple PDFs at once.
    pdf_records format: [(title, drive_link, class_tag, is_free, search_keywords), ...]
    Returns the number of PDFs successfully inserted.
    """
    async with pool.acquire() as conn:
        try:
            insert_query = """
                INSERT INTO pdfs (title, drive_link, class_tag, is_free, search_keywords)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (pdf_id) DO NOTHING;
            """
            
            await conn.executemany(insert_query, pdf_records)
            logging.info(f"✅ Bulk inserted {len(pdf_records)} PDFs")
            return len(pdf_records)
            
        except Exception as e:
            logging.error(f"Bulk PDF insert error: {e}")
            return 0

async def get_pdf_statistics(pool: asyncpg.Pool) -> dict:
    """
    Get statistics about PDFs in the database.
    Returns a dict with counts by class and free/paid status.
    """
    async with pool.acquire() as conn:
        try:
            stats = await conn.fetch("""
                SELECT 
                    class_tag,
                    COUNT(*) as total,
                    SUM(CASE WHEN is_free THEN 1 ELSE 0 END) as free_count,
                    SUM(CASE WHEN NOT is_free THEN 1 ELSE 0 END) as paid_count
                FROM pdfs
                GROUP BY class_tag
                ORDER BY class_tag;
            """)
            
            result = {}
            for row in stats:
                result[row['class_tag']] = {
                    'total': row['total'],
                    'free': row['free_count'],
                    'paid': row['paid_count']
                }
            
            return result
            
        except Exception as e:
            logging.error(f"Error getting PDF statistics: {e}")
            return {}

# ============================================================================
# SEARCH OPTIMIZATION UTILITIES
# ============================================================================

async def rebuild_search_index(pool: asyncpg.Pool) -> bool:
    """
    Rebuild the full-text search indexes for better performance.
    Should be run periodically by admin.
    """
    async with pool.acquire() as conn:
        try:
            # Reindex the GIN index
            await conn.execute("REINDEX INDEX idx_pdfs_keywords;")
            logging.info("✅ Successfully rebuilt PDF search indexes")
            return True
        except Exception as e:
            logging.error(f"Error rebuilding search index: {e}")
            return False