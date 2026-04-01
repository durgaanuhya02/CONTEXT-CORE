#!/bin/bash
# Run this once to initialize and index the dataset with GraphRAG

echo "Step 1: Initialize GraphRAG in dataset folder"
graphrag init --root ../../dataset

echo ""
echo "Step 2: Add your OpenAI API key to ../../dataset/.env"
echo "  GRAPHRAG_API_KEY=your_key_here"
echo ""
echo "Step 3: Run indexing (this will take 5-15 minutes and cost ~$0.50-2.00)"
echo "  graphrag index --root ../../dataset"
echo ""
echo "Step 4: After indexing, run the metadata linker"
echo "  python metadata_linker.py"
echo ""
echo "Step 5: Start the backend"
echo "  cd ../backend && uvicorn main:app --reload"
echo ""
echo "Step 6: Start the frontend"
echo "  cd ../frontend && npm install && npm run dev"
