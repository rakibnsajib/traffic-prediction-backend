MERGE (a:Intersection {code: "A", name: "Node A", lat: 23.8103, lng: 90.4125})
MERGE (b:Intersection {code: "B", name: "Node B", lat: 23.8050, lng: 90.3950})
MERGE (c:Intersection {code: "C", name: "Node C", lat: 23.7985, lng: 90.3700})
MERGE (d:Intersection {code: "D", name: "Node D", lat: 23.7900, lng: 90.3400})
MERGE (e:Intersection {code: "E", name: "Node E", lat: 23.7806, lng: 90.2794})
MERGE (f:Intersection {code: "F", name: "Node F", lat: 23.7855, lng: 90.3100})
MERGE (g:Intersection {code: "G", name: "Node G", lat: 23.8000, lng: 90.3250})
MERGE (h:Intersection {code: "H", name: "Node H", lat: 23.8120, lng: 90.3550});

MATCH (a:Intersection {code: "A"}), (b:Intersection {code: "B"})
MERGE (a)-[:ROAD_SEGMENT {
    segment_id: "R101",
    distance_km: 2.0,
    predicted_speed: 28.5,
    predicted_time: 4.21,
    congestion_level: "Medium"
}]->(b);

MATCH (b:Intersection {code: "B"}), (c:Intersection {code: "C"})
MERGE (b)-[:ROAD_SEGMENT {
    segment_id: "R102",
    distance_km: 2.5,
    predicted_speed: 22.5,
    predicted_time: 6.67,
    congestion_level: "High"
}]->(c);

MATCH (c:Intersection {code: "C"}), (d:Intersection {code: "D"})
MERGE (c)-[:ROAD_SEGMENT {
    segment_id: "R103",
    distance_km: 2.8,
    predicted_speed: 26.8,
    predicted_time: 6.27,
    congestion_level: "Medium"
}]->(d);

