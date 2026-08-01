from typing import List

class QueryDecomposer:
    def __init__(self, llm):
        self.llm = llm

    def decompose(self, query: str) -> List[str]:
        prompt = (
            f"You are a query decomposition assistant.\n"
            f"Break down the user's complex query into a list of independent, self-contained search queries.\n"
            f"Respond ONLY with a bulleted list of queries, starting each line with a hyphen (-).\n"
            f"Do not write any introductory or concluding text.\n\n"
            f"Complex Query: '{query}'\n\n"
            f"Sub-queries:"
        )
        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # Fast Python parsing of bullet points
            sub_queries = []
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("-"):
                    sub_query = line.lstrip("-").strip()
                    if sub_query:
                        sub_queries.append(sub_query)
            
            # If parsing failed to extract anything, fall back to the original query
            return sub_queries if sub_queries else [query]
            
        except Exception as e:
            print(f"[Query Decomposer] Error during decomposition: {e}")
            return [query]
