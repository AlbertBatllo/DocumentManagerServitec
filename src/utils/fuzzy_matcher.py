"""
Fuzzy matching utilities for name-based document search and duplicate detection.

This module provides fuzzy string matching capabilities to help users find documents
even when they don't remember the exact name, and to prevent creation of near-duplicate
documents with very similar names.
"""

import difflib
from typing import List, Tuple, Optional
import re


class FuzzyMatcher:
    """
    Fuzzy string matching utility for document names.
    
    Uses Python's built-in difflib for efficient fuzzy matching operations.
    """
    
    DEFAULT_SIMILARITY_THRESHOLD = 0.8  # 80% similarity
    DUPLICATE_THRESHOLD = 0.9  # 90% similarity for duplicate detection
    
    def __init__(self, similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD):
        """
        Initialize fuzzy matcher with similarity threshold.
        
        Args:
            similarity_threshold: Minimum similarity ratio (0.0 to 1.0) for matches
        """
        self.similarity_threshold = similarity_threshold
    
    def normalize_string(self, text: str) -> str:
        """
        Normalize string for better matching by:
        - Converting to lowercase
        - Removing extra whitespace
        - Standardizing common abbreviations
        
        Args:
            text: Input string to normalize
            
        Returns:
            Normalized string
        """
        if not text:
            return ""
        
        # Convert to lowercase and strip whitespace
        normalized = text.lower().strip()
        
        # Remove multiple spaces
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Standardize common abbreviations/variations
        replacements = {
            'plano': 'plano',
            'pl ': 'plano ',
            'pl-': 'plano-',
            'cert': 'certificacion',
            'certificación': 'certificacion',
            'licitación': 'licitacion',
            'licit': 'licitacion',
        }
        
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
        
        return normalized
    
    def calculate_similarity(self, string1: str, string2: str) -> float:
        """
        Calculate similarity ratio between two strings.
        
        Args:
            string1: First string
            string2: Second string
            
        Returns:
            Similarity ratio between 0.0 and 1.0
        """
        if not string1 or not string2:
            return 0.0
        
        # Normalize both strings
        norm1 = self.normalize_string(string1)
        norm2 = self.normalize_string(string2)
        
        # Use SequenceMatcher for fuzzy comparison
        matcher = difflib.SequenceMatcher(None, norm1, norm2)
        return matcher.ratio()
    
    def find_similar_names(self, query: str, name_list: List[str], 
                          threshold: Optional[float] = None) -> List[Tuple[str, float]]:
        """
        Find names similar to the query string.
        
        Args:
            query: Query string to match against
            name_list: List of names to search through
            threshold: Similarity threshold (uses instance default if None)
            
        Returns:
            List of tuples (name, similarity_score) sorted by similarity descending
        """
        if threshold is None:
            threshold = self.similarity_threshold
        
        results = []
        
        for name in name_list:
            similarity = self.calculate_similarity(query, name)
            if similarity >= threshold:
                results.append((name, similarity))
        
        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results
    
    def is_potential_duplicate(self, name1: str, name2: str) -> bool:
        """
        Check if two names are potential duplicates (very high similarity).
        
        Args:
            name1: First name
            name2: Second name
            
        Returns:
            True if names are potential duplicates
        """
        similarity = self.calculate_similarity(name1, name2)
        return similarity >= self.DUPLICATE_THRESHOLD
    
    def get_best_match(self, query: str, name_list: List[str]) -> Optional[str]:
        """
        Get the best matching name from a list.
        
        Args:
            query: Query string
            name_list: List of names to search
            
        Returns:
            Best matching name or None if no good match found
        """
        if not name_list:
            return None
        
        # Use difflib's get_close_matches for best performance
        matches = difflib.get_close_matches(
            self.normalize_string(query),
            [self.normalize_string(name) for name in name_list],
            n=1,
            cutoff=self.similarity_threshold
        )
        
        if matches:
            # Find the original name corresponding to the normalized match
            normalized_query = matches[0]
            for original_name in name_list:
                if self.normalize_string(original_name) == normalized_query:
                    return original_name
        
        return None
    
    def suggest_alternatives(self, query: str, name_list: List[str], 
                           max_suggestions: int = 5) -> List[str]:
        """
        Suggest alternative names based on partial matches.
        
        Args:
            query: Query string
            name_list: List of available names
            max_suggestions: Maximum number of suggestions to return
            
        Returns:
            List of suggested names
        """
        # Use a lower threshold for suggestions
        suggestion_threshold = max(0.3, self.similarity_threshold - 0.2)
        
        matches = self.find_similar_names(query, name_list, suggestion_threshold)
        
        # Return up to max_suggestions names
        return [name for name, score in matches[:max_suggestions]]
    
    def contains_fuzzy(self, query: str, text: str) -> bool:
        """
        Check if query is contained within text using fuzzy matching.
        Useful for search functionality.
        
        Args:
            query: Query string to search for
            text: Text to search within
            
        Returns:
            True if query is fuzzily contained in text
        """
        if not query or not text:
            return False
        
        query_norm = self.normalize_string(query)
        text_norm = self.normalize_string(text)
        
        # Direct substring match
        if query_norm in text_norm:
            return True
        
        # Fuzzy word matching - check if individual words match
        query_words = query_norm.split()
        text_words = text_norm.split()
        
        for query_word in query_words:
            word_found = False
            for text_word in text_words:
                # Check for fuzzy match between words
                similarity = difflib.SequenceMatcher(None, query_word, text_word).ratio()
                if similarity >= 0.7:  # 70% similarity for word matching
                    word_found = True
                    break
            
            if not word_found:
                return False
        
        return True


# Global instance for convenience
default_matcher = FuzzyMatcher()

# Convenience functions using the default matcher
def find_similar_names(query: str, name_list: List[str]) -> List[Tuple[str, float]]:
    """Find similar names using default matcher."""
    return default_matcher.find_similar_names(query, name_list)

def is_potential_duplicate(name1: str, name2: str) -> bool:
    """Check for potential duplicates using default matcher."""
    return default_matcher.is_potential_duplicate(name1, name2)

def get_best_match(query: str, name_list: List[str]) -> Optional[str]:
    """Get best match using default matcher."""
    return default_matcher.get_best_match(query, name_list)

def fuzzy_search(query: str, text: str) -> bool:
    """Check if query fuzzily matches text using default matcher."""
    return default_matcher.contains_fuzzy(query, text)