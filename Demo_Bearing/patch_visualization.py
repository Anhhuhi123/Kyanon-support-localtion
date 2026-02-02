#!/usr/bin/env python3
"""
Script to patch visualization_advanced.html with new features:
1. Fix bearing description
2. Add distance matrix display
3. Add bearing normalization explanation
"""

import re

def patch_html_file(input_file, output_file):
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Add buildDistanceMatrix function after calculateBearingDifference
    distance_matrix_func = '''
        function buildDistanceMatrix() {
            // Build distance matrix: [n+1][n+1] where index 0 = USER
            const n = pois.length;
            const matrix = Array(n + 1).fill(0).map(() => Array(n + 1).fill(0));
            
            // All coordinates: [USER, POI1, POI2, ..., POIn]
            const coords = [
                { lat: userLocation.lat, lon: userLocation.lon },
                ...pois.map(p => ({ lat: p.lat, lon: p.lon }))
            ];
            
            for (let i = 0; i <= n; i++) {
                for (let j = 0; j <= n; j++) {
                    if (i !== j) {
                        matrix[i][j] = calculateDistance(
                            coords[i].lat, coords[i].lon,
                            coords[j].lat, coords[j].lon
                        );
                    }
                }
            }
            
            return matrix;
        }
'''
    
    # Find position after calculateBearingDifference
    pattern = r'(function calculateBearingDifference\([^}]+\})'
    content = re.sub(pattern, r'\1\n' + distance_matrix_func, content)
    
    # 2. Add bearing explanation box in displayAnalysis
    bearing_explanation = '''
            // Bearing explanation
            let bearingExplanation = '';
            if (!isFirst) {
                const prevPosName = routeIndex === 1 ? 'USER' : `POI #${routeIndex - 1}`;
                const currPosName = `POI #${routeIndex}`;
                
                bearingExplanation = `
                    <div class="formula-box" style="background: #fff3cd; border-left: 3px solid #ff9800;">
                        <strong>🧭 Giải thích Bearing:</strong><br>
                        <strong>Vector 1:</strong> ${prevPosName} → ${currPosName}<br>
                        <strong>Vector 2:</strong> ${currPosName} → ${poi.name}<br>
                        <strong>Góc Δ:</strong> Chênh lệch giữa 2 vector<br>
                        <strong>Bearing Score:</strong> 1 - (Δ / 180°) = ${selectedComp.bearingScore.toFixed(3)}<br>
                        <em style="font-size: 10px;">• 0° (cùng hướng) = 1.0 (tốt nhất)<br>
                        • 180° (ngược hướng) = 0.0 (tệ nhất)</em>
                    </div>
                `;
            }
            
            // Add to HTML before score breakdown
            html += bearingExplanation;
'''
    
    # Insert before score breakdown section
    pattern = r'(// Score breakdown\s+html \+= `)'
    content = re.sub(pattern, bearing_explanation + r'\n\1', content)
    
    # 3. Add distance matrix display
    distance_matrix_display = '''
            // Distance matrix for route POIs
            if (route.length > 0) {
                html += `
                    <h4 style="margin: 15px 0 10px 0; font-size: 12px; color: #666; font-weight: 600;">
                        📐 Distance Matrix (Route POIs):
                    </h4>
                    <div style="overflow-x: auto; max-height: 200px; overflow-y: auto;">
                        <table class="comparison-table">
                            <thead>
                                <tr>
                                    <th style="position: sticky; left: 0; background: #667eea; z-index: 2;">From \\\\ To</th>
                                    <th>USER</th>
                `;
                
                route.forEach((p, idx) => {
                    html += `<th>POI #${idx + 1}</th>`;
                });
                
                html += `</tr></thead><tbody>`;
                
                // USER row
                html += `<tr><td style="position: sticky; left: 0; background: #f5f7ff; font-weight: 600;">USER</td><td>0</td>`;
                route.forEach(p => {
                    const dist = calculateDistance(userLocation.lat, userLocation.lon, p.lat, p.lon);
                    html += `<td>${dist.toFixed(0)}m</td>`;
                });
                html += `</tr>`;
                
                // POI rows
                route.forEach((fromPoi, i) => {
                    html += `<tr><td style="position: sticky; left: 0; background: #f5f7ff; font-weight: 600;">POI #${i + 1}</td>`;
                    
                    const distToUser = calculateDistance(fromPoi.lat, fromPoi.lon, userLocation.lat, userLocation.lon);
                    html += `<td>${distToUser.toFixed(0)}m</td>`;
                    
                    route.forEach((toPoi, j) => {
                        if (i === j) {
                            html += `<td>0</td>`;
                        } else {
                            const dist = calculateDistance(fromPoi.lat, fromPoi.lon, toPoi.lat, toPoi.lon);
                            html += `<td>${dist.toFixed(0)}m</td>`;
                        }
                    });
                    html += `</tr>`;
                });
                
                html += `</tbody></table></div>`;
            }
'''
    
    # Insert before reasoning section
    pattern = r"(// Reasoning\s+html \+= `)"
    content = re.sub(pattern, distance_matrix_display + r'\n\1', content)
    
    # Write output
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Patched {input_file} → {output_file}")
    print("   - Added buildDistanceMatrix() function")
    print("   - Added bearing explanation box")
    print("   - Added distance matrix table")

if __name__ == '__main__':
    patch_html_file('visualization_advanced.html', 'visualization_advanced_fixed.html')
    print("\n🎉 Done! Open visualization_advanced_fixed.html")
    print("visuzalization algorithm bearing test")
    print("test pull request part 2")


