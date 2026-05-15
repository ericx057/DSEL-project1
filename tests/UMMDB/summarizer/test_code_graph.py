from UMMDB.summarizer.code_graph import CodeGraph

def test_code_graph_empty():
    cg = CodeGraph()
    assert cg.calculate_centrality() == {}
    assert cg.get_top_percentile_nodes() == []

def test_code_graph_single_node():
    cg = CodeGraph()
    cg.add_node("A")
    centrality = cg.calculate_centrality()
    assert centrality == {"A": 0.0}
    assert cg.get_top_percentile_nodes(0.8) == ["A"]

def test_code_graph_centrality():
    cg = CodeGraph()
    # Create a star graph where A is the center
    cg.add_edge("B", "A", "calls")
    cg.add_edge("C", "A", "calls")
    cg.add_edge("A", "D", "uses")
    cg.add_edge("A", "E", "uses")
    
    # Also add some nodes to test metadata
    cg.add_node("F", {"tier": "T-1"})
    
    centrality = cg.calculate_centrality()
    
    # A should have the highest centrality
    assert centrality["A"] > centrality["B"]
    
    top_nodes = cg.get_top_percentile_nodes(0.8)
    assert "A" in top_nodes

def test_code_graph_100th_percentile():
    cg = CodeGraph()
    cg.add_edge("B", "A", "calls")
    cg.add_edge("C", "A", "calls")
    
    # Using percentile=1.0 will trigger the index capping
    top_nodes = cg.get_top_percentile_nodes(1.0)
    assert len(top_nodes) > 0

def test_code_graph_disconnected_components():
    cg = CodeGraph()
    cg.add_edge("A", "B", "calls")
    cg.add_edge("B", "C", "calls")
    
    cg.add_edge("D", "E", "calls")
    cg.add_edge("E", "F", "calls")
    
    centrality = cg.calculate_centrality()
    
    # B and E should be central in their respective components
    assert centrality["B"] > 0
    assert centrality["E"] > 0
    assert centrality["A"] == 0
    assert centrality["C"] == 0
    
    top_nodes = cg.get_top_percentile_nodes(0.8)
    assert "B" in top_nodes
    assert "E" in top_nodes
