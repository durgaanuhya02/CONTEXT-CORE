#!/bin/bash
# ContextCore — Full preprocessing pipeline
# Run this once before starting the backend.

set -e

echo "=== Step 1: Install spaCy + NetworkX ==="
pip install spacy networkx
python -m spacy download en_core_web_lg || python -m spacy download en_core_web_sm

echo ""
echo "=== Step 2: spaCy NER extraction ==="
python preprocess.py

echo ""
echo "=== Step 3: Build NetworkX knowledge graph ==="
python build_graph.py

echo ""
echo "=== Step 4: Run metadata linker (requires Postgres + GraphRAG output) ==="
python metadata_linker.py

echo ""
echo "Pipeline complete."
echo "Graph JSON: ../../dataset/ner_output/knowledge_graph.json"
echo "GraphML:    ../../dataset/ner_output/knowledge_graph.graphml"
