class SynapseGraphRenderer {
    constructor(svgId) {
        this.svg = d3.select(`#${svgId}`);
        this.width = this.svg.node().getBoundingClientRect().width;
        this.height = this.svg.node().getBoundingClientRect().height;
        
        // Define arrowheads for edges
        this.svg.append("defs").append("marker")
            .attr("id", "arrow")
            .attr("viewBox", "0 -5 10 10")
            .attr("refX", 18)
            .attr("refY", 0)
            .attr("markerWidth", 6)
            .attr("markerHeight", 6)
            .attr("orient", "auto")
            .append("path")
            .attr("d", "M0,-5L10,0L0,5")
            .attr("fill", "rgba(255, 255, 255, 0.25)");

        this.g = this.svg.append("g").attr("class", "zoom-container");
        
        // Add zoom behaviors
        this.zoomBehavior = d3.zoom()
            .scaleExtent([0.1, 4])
            .on("zoom", (event) => {
                this.g.attr("transform", event.transform);
                this._semanticZoom(event.transform.k);
            });
            
        this.svg.call(this.zoomBehavior);

        this.simulation = d3.forceSimulation()
            .force("link", d3.forceLink().id(d => d.id).distance(100))
            .force("charge", d3.forceManyBody().strength(-200))
            .force("center", d3.forceCenter(this.width / 2, this.height / 2))
            .force("collision", d3.forceCollide().radius(25));

        this.nodes = [];
        this.edges = [];
        this.onClickCallback = null;
        
        window.addEventListener("resize", () => this.resize());
    }

    resize() {
        const rect = this.svg.node().getBoundingClientRect();
        this.width = rect.width;
        this.height = rect.height;
        this.simulation.force("center", d3.forceCenter(this.width / 2, this.height / 2));
        this.simulation.alpha(0.3).restart();
    }

    zoomIn() {
        this.svg.transition().duration(300).call(this.zoomBehavior.scaleBy, 1.3);
    }

    zoomOut() {
        this.svg.transition().duration(300).call(this.zoomBehavior.scaleBy, 0.75);
    }

    resetZoom() {
        this.svg.transition().duration(300).call(
            this.zoomBehavior.transform, 
            d3.zoomIdentity.translate(0, 0).scale(1)
        );
    }

    update(nodes, edges, onClickCallback) {
        this.nodes = JSON.parse(JSON.stringify(nodes)); // Deep clone
        this.edges = JSON.parse(JSON.stringify(edges));
        this.onClickCallback = onClickCallback;

        // Clean up previous groups
        this.g.selectAll("*").remove();

        // Color mapping based on node kind
        const colors = {
            "package": "var(--accent-package)",
            "module": "var(--accent-module)",
            "class": "var(--accent-class)",
            "function": "var(--accent-function)",
            "document": "var(--accent-document)",
            "context": "var(--accent-historical)"
        };

        const defaultColor = "var(--text-secondary)";

        // Draw Links
        const link = this.g.append("g")
            .selectAll("line")
            .data(this.edges)
            .join("line")
            .attr("class", "edge")
            .attr("stroke", "rgba(255, 255, 255, 0.15)")
            .attr("marker-end", "url(#arrow)");

        // Draw Nodes
        const node = this.g.append("g")
            .selectAll("g")
            .data(this.nodes)
            .join("g")
            .attr("class", d => `node status-${d.status || 'active'}`)
            .call(this._drag(this.simulation));

        node.append("circle")
            .attr("r", d => d.kind === "package" ? 14 : 10)
            .attr("class", d => `node-circle ${d.kind} status-${d.status || 'active'}`)
            .style("fill", d => {
                if (d.status === "invalidated") {
                    return "var(--bg-surface)";
                }
                return "var(--bg-surface)";
            })
            .style("stroke", d => {
                if (d.status === "invalidated") {
                    return "var(--accent-historical)";
                }
                return colors[d.kind] || defaultColor;
            })
            .style("stroke-width", d => d.kind === "package" ? "3px" : "2px");

        node.append("text")
            .attr("dx", 18)
            .attr("dy", 4)
            .attr("class", "node-label")
            .text(d => d.label)
            .style("opacity", d => d.status === "invalidated" ? 0.4 : 0.9)
            .style("text-decoration", d => d.status === "invalidated" ? "line-through" : "none");

        // Interactivity (hover/click)
        node.on("click", (event, d) => {
            if (this.onClickCallback) {
                this.onClickCallback(d);
            }
            event.stopPropagation();
        });

        node.on("mouseover", (event, d) => {
            const tooltip = d3.select("#graph-tooltip");
            tooltip.style("display", "block")
                .html(`
                    <div style="font-weight: 600; font-family: var(--font-heading); color: var(--text-primary); margin-bottom: 4px;">${d.label}</div>
                    <div style="font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); margin-bottom: 8px; font-weight: 700;">${d.kind}</div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 11px;">
                        <span>Status:</span>
                        <span style="text-transform: capitalize; font-weight: 500; color: var(--text-secondary);">${d.status || 'active'}</span>
                    </div>
                    ${d.status === 'invalidated' ? '<div style="border: 1px solid rgba(255,255,255,0.08); background: rgba(255,255,255,0.02); color: var(--text-muted); font-size: 10px; padding: 4px 6px; border-radius: 4px; margin-top: 8px; font-weight: 500;">Invalidated</div>' : ''}
                `)
                .style("left", (event.pageX + 15) + "px")
                .style("top", (event.pageY - 15) + "px");

            // Highlight connections on hover
            const connectedNodeIds = new Set();
            connectedNodeIds.add(d.id);
            
            link.style("stroke-opacity", e => {
                if (e.source.id === d.id || e.target.id === d.id) {
                    connectedNodeIds.add(e.source.id);
                    connectedNodeIds.add(e.target.id);
                    return 0.8;
                }
                return 0.05;
            }).style("stroke", e => {
                if (e.source.id === d.id || e.target.id === d.id) {
                    return "var(--text-primary)";
                }
                return "rgba(255, 255, 255, 0.05)";
            }).classed("active-flow", e => e.source.id === d.id || e.target.id === d.id);

            node.style("opacity", n => connectedNodeIds.has(n.id) ? 1.0 : 0.25);
        });

        node.on("mousemove", (event) => {
            d3.select("#graph-tooltip")
                .style("left", (event.pageX + 15) + "px")
                .style("top", (event.pageY - 15) + "px");
        });

        node.on("mouseout", () => {
            d3.select("#graph-tooltip").style("display", "none");
            link.style("stroke-opacity", 0.25)
                .style("stroke", "rgba(255, 255, 255, 0.15)")
                .classed("active-flow", false);
            node.style("opacity", 1.0);
        });

        // Set simulation datasets
        this.simulation.nodes(this.nodes);
        this.simulation.force("link").links(this.edges);
        
        this.simulation.alpha(1).restart();

        this.simulation.on("tick", () => {
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);

            node
                .attr("transform", d => `translate(${d.x}, ${d.y})`);
        });
    }

    _drag(simulation) {
        return d3.drag()
            .on("start", (event, d) => {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            })
            .on("drag", (event, d) => {
                d.fx = event.x;
                d.fy = event.y;
            })
            .on("end", (event, d) => {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            });
    }

    _semanticZoom(scale) {
        const labels = this.g.selectAll("text");
        if (scale < 0.6) {
            labels.attr("display", "none");
        } else {
            labels.attr("display", "block");
        }
    }
}
