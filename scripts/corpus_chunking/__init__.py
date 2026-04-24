"""Corpus chunking pipeline (M2 spec §3).

Three-stage LLM pipeline: scene_segmenter → chunk_tagger → chunk_indexer.
Outputs TaggedChunks to Qdrant ``corpus_chunks`` collection.
"""
