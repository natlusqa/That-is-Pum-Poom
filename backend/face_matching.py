"""
Vectorized face matching using numpy matrix operations.
~100x faster than Python for-loop comparison for 100+ employees.
"""
import numpy as np


def build_face_matrix(known_faces):
    """
    Pre-stack known face vectors into a normalized matrix for fast matching.

    Args:
        known_faces: list of (emp_id, name, vector_512) tuples

    Returns:
        (normed_matrix, ids, names) where normed_matrix is (N, 512) pre-normalized
    """
    if not known_faces:
        return np.empty((0, 512), dtype=np.float32), [], []

    ids = []
    names = []
    vectors = []

    for emp_id, name, vec in known_faces:
        if isinstance(vec, (list, tuple)):
            vec = np.array(vec, dtype=np.float32)
        if vec.shape[0] == 512:
            vectors.append(vec)
            ids.append(emp_id)
            names.append(name)

    if not vectors:
        return np.empty((0, 512), dtype=np.float32), [], []

    matrix = np.stack(vectors)  # (N, 512)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-6
    normed_matrix = matrix / norms

    return normed_matrix, ids, names


def match_face(query_embedding, normed_matrix, ids, names, threshold=0.5):
    """
    Find the best matching face using vectorized cosine similarity.

    Args:
        query_embedding: (512,) numpy array from camera
        normed_matrix: (N, 512) pre-normalized matrix from build_face_matrix
        ids: list of employee IDs
        names: list of employee names
        threshold: minimum similarity score

    Returns:
        (emp_id, name, similarity) or (None, None, 0.0)
    """
    if normed_matrix.shape[0] == 0:
        return None, None, 0.0

    query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-6)
    similarities = normed_matrix @ query_norm  # (N,) vectorized dot product

    best_idx = int(np.argmax(similarities))
    best_sim = float(similarities[best_idx])

    if best_sim > threshold:
        return ids[best_idx], names[best_idx], best_sim

    return None, None, best_sim


def match_faces_batch(query_embeddings, normed_matrix, ids, names, threshold=0.5):
    """
    Match multiple faces at once (batch mode).

    Args:
        query_embeddings: (M, 512) numpy array of M face embeddings
        normed_matrix: (N, 512) pre-normalized matrix
        ids, names: employee info
        threshold: minimum similarity

    Returns:
        list of (emp_id, name, similarity) for each query
    """
    if normed_matrix.shape[0] == 0 or len(query_embeddings) == 0:
        return [(None, None, 0.0)] * len(query_embeddings)

    query_norms = np.linalg.norm(query_embeddings, axis=1, keepdims=True) + 1e-6
    normed_queries = query_embeddings / query_norms
    sim_matrix = normed_queries @ normed_matrix.T  # (M, N)

    results = []
    for i in range(sim_matrix.shape[0]):
        best_idx = int(np.argmax(sim_matrix[i]))
        best_sim = float(sim_matrix[i, best_idx])
        if best_sim > threshold:
            results.append((ids[best_idx], names[best_idx], best_sim))
        else:
            results.append((None, None, best_sim))

    return results
