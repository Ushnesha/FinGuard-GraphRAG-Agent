import os
import json
import openai

client = openai.OpenAI(
    api_key="none",
    base_url="http://localhost:11434/v1"
)

prompt = """Identify all key Entities and Relationships in the text below.

Allowed Entity Types: [COMPANY, BUSINESS_SEGMENT, FINANCIAL_METRIC, TIME_PERIOD]
Allowed Relationship Types: [PART_OF, REPORTS, FOR_PERIOD, ACQUIRED]

You must format your response STRICTLY as a valid JSON object matching this structure:
{
    "entities": [
        {"name": "entity name", "type": "ENTITY_TYPE"}
    ],
    "relationships": [
        {"source": "source_entity_name", "type": "RELATIONSHIP_TYPE", "target": "target_entity_name"}
    ]
}

Formatting constraints:
1. Use exactly "name" (not "id" or "text") for the entity name.
2. Use exactly "type" (not "relationship_type" or "label") for the relationship type.
3. CRITICAL: Every element in the "entities" list MUST be a full object with "name" and "type". Under NO circumstances should you return plain strings in the "entities" list.
4. If no entities or relationships are found, return empty lists: {"entities": [], "relationships": []}

Return ONLY valid JSON. Do not include any explanation or markdown formatting outside of the JSON block.

Text:
"Project Alpha is our primary cloud migration effort, managed by Sarah."
"""

print("Sending request with stop sequences...")
try:
    resp = client.chat.completions.create(
        model="meta-llama/Meta-Llama-3-8B-Instruct",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=1000,
        stop=["<|eot_id|>", "<|end_of_text|>"]
    )
    print("FINISH REASON:", resp.choices[0].finish_reason)
    print("USAGE:", resp.usage)
    print("CONTENT:")
    print(repr(resp.choices[0].message.content))
except Exception as e:
    print("Error:", e)
