import type { EvidenceGraph, EvidenceGraphEdge, EvidenceGraphNode } from '../api/types';

const TYPE_ORDER = [
    'Institution',
    'Person',
    'PolicyEvent',
    'DocumentVersion',
    'Chunk',
    'MacroTopic',
    'MacroSeries',
    'MacroRelease',
    'Instrument',
];

const MAX_NODES = 60;
const MAX_EDGES = 120;
const COL_W = 200;
const ROW_H = 54;
const NODE_W = 160;
const NODE_H = 36;
const PAD = 24;

interface Placed {
    node: EvidenceGraphNode;
    x: number;
    y: number;
    col: number;
}

function truncate(text: string, max = 22): string {
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/**
 * Bounded, deterministic graph view: nodes are placed in columns by ontology type
 * and sorted by id inside a column, so the same graph always renders the same way.
 */
export function EvidenceGraphView({
    graph,
    selectedEdgeId,
    selectedNodeId,
    onSelectEdge,
    onSelectNode,
}: {
    graph: EvidenceGraph;
    selectedEdgeId?: string;
    selectedNodeId?: string;
    onSelectEdge: (edge: EvidenceGraphEdge) => void;
    onSelectNode: (node: EvidenceGraphNode) => void;
}) {
    const nodes = [...graph.nodes].sort((a, b) => a.nodeId.localeCompare(b.nodeId)).slice(0, MAX_NODES);
    const nodeIds = new Set(nodes.map(n => n.nodeId));
    const edges = graph.edges
        .filter(e => nodeIds.has(e.subjectId) && nodeIds.has(e.objectId))
        .sort((a, b) => a.assertionId.localeCompare(b.assertionId))
        .slice(0, MAX_EDGES);
    const truncated = graph.nodes.length > nodes.length || graph.edges.length > edges.length;

    const types = [...new Set(nodes.map(n => n.nodeType))].sort((a, b) => {
        const ia = TYPE_ORDER.indexOf(a);
        const ib = TYPE_ORDER.indexOf(b);
        return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
    });
    const placed = new Map<string, Placed>();
    let maxRows = 0;
    types.forEach((type, col) => {
        const inCol = nodes.filter(n => n.nodeType === type);
        maxRows = Math.max(maxRows, inCol.length);
        inCol.forEach((node, row) => {
            placed.set(node.nodeId, { node, col, x: PAD + col * COL_W, y: PAD + 22 + row * ROW_H });
        });
    });
    const width = PAD * 2 + Math.max(1, types.length) * COL_W - (COL_W - NODE_W);
    const height = PAD * 2 + 22 + Math.max(1, maxRows) * ROW_H;

    if (nodes.length === 0) {
        return <p className="fi-muted-note">The graph view for this bundle has no nodes.</p>;
    }

    const edgePath = (e: EvidenceGraphEdge) => {
        const s = placed.get(e.subjectId)!;
        const o = placed.get(e.objectId)!;
        if (s.col === o.col) {
            const x = s.x + NODE_W;
            const y1 = s.y + NODE_H / 2;
            const y2 = o.y + NODE_H / 2;
            const bulge = 40 + Math.abs(y2 - y1) * 0.15;
            return { d: `M ${x} ${y1} C ${x + bulge} ${y1}, ${x + bulge} ${y2}, ${x} ${y2}`, mx: x + bulge * 0.75, my: (y1 + y2) / 2 };
        }
        const forward = s.col < o.col;
        const x1 = forward ? s.x + NODE_W : s.x;
        const x2 = forward ? o.x : o.x + NODE_W;
        const y1 = s.y + NODE_H / 2;
        const y2 = o.y + NODE_H / 2;
        const dx = (x2 - x1) / 2;
        return { d: `M ${x1} ${y1} C ${x1 + dx} ${y1}, ${x2 - dx} ${y2}, ${x2} ${y2}`, mx: (x1 + x2) / 2, my: (y1 + y2) / 2 };
    };

    return (
        <div className="fi-graph">
            {truncated && (
                <p className="fi-muted-note">
                    <i className="fas fa-compress"></i> Display bounded to {MAX_NODES} nodes and {MAX_EDGES} edges
                    ({graph.nodes.length} nodes, {graph.edges.length} edges returned).
                </p>
            )}
            {(graph.limitsHit ?? []).length > 0 && (
                <p className="fi-muted-note"><i className="fas fa-ruler"></i> Traversal limits hit: {(graph.limitsHit ?? []).join(', ')}</p>
            )}
            <div className="fi-graph-scroll">
                <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Evidence graph">
                    <defs>
                        <marker id="fi-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--text-secondary)" />
                        </marker>
                    </defs>
                    {types.map((type, col) => (
                        <text key={type} x={PAD + col * COL_W} y={PAD + 8} className="fi-graph-coltitle">{type}</text>
                    ))}
                    {edges.map(e => {
                        const { d, mx, my } = edgePath(e);
                        const selected = e.assertionId === selectedEdgeId;
                        const review = e.validationStatus && e.validationStatus !== 'approved';
                        return (
                            <g key={e.assertionId} className={`fi-graph-edge ${selected ? 'selected' : ''} ${review ? 'review' : ''}`}
                                onClick={() => onSelectEdge(e)} role="button" tabIndex={0}
                                onKeyDown={ev => { if (ev.key === 'Enter' || ev.key === ' ') onSelectEdge(e); }}>
                                <title>{`${e.relation} (${e.assertionId})`}</title>
                                <path d={d} className="fi-graph-edge-hit" />
                                <path d={d} className="fi-graph-edge-line" markerEnd="url(#fi-arrow)" />
                                <text x={mx} y={my - 4} className="fi-graph-edge-label" textAnchor="middle">{e.relation}</text>
                            </g>
                        );
                    })}
                    {[...placed.values()].map(({ node, x, y }) => {
                        const selected = node.nodeId === selectedNodeId;
                        return (
                            <g key={node.nodeId} className={`fi-graph-node fi-graph-node-${node.nodeType} ${selected ? 'selected' : ''}`}
                                transform={`translate(${x}, ${y})`} onClick={() => onSelectNode(node)} role="button" tabIndex={0}
                                onKeyDown={ev => { if (ev.key === 'Enter' || ev.key === ' ') onSelectNode(node); }}>
                                <title>{`${node.nodeType}: ${node.label} (${node.nodeId})`}</title>
                                <rect width={NODE_W} height={NODE_H} rx={6} />
                                <text x={10} y={15} className="fi-graph-node-label">{truncate(node.label)}</text>
                                <text x={10} y={29} className="fi-graph-node-type">{truncate(node.nodeId, 26)}</text>
                            </g>
                        );
                    })}
                </svg>
            </div>
        </div>
    );
}
