interface PaginationProps {
    page: number;
    pageSize: number;
    totalCount: number;
    onPage: (page: number) => void;
    label?: string;
}

export function Pagination({ page, pageSize, totalCount, onPage, label = 'items' }: PaginationProps) {
    const pages = Math.max(1, Math.ceil(totalCount / Math.max(1, pageSize)));
    if (totalCount <= pageSize && page === 1) {
        return <div className="fi-pagination fi-pagination-single">{totalCount} {label}</div>;
    }
    const first = (page - 1) * pageSize + 1;
    const last = Math.min(totalCount, page * pageSize);
    return (
        <nav className="fi-pagination" aria-label={`${label} pagination`}>
            <button onClick={() => onPage(1)} disabled={page <= 1} aria-label="First page">
                <i className="fas fa-angle-double-left"></i>
            </button>
            <button onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="Previous page">
                <i className="fas fa-angle-left"></i>
            </button>
            <span className="fi-pagination-info">
                {first}–{last} of {totalCount} {label} · page {page}/{pages}
            </span>
            <button onClick={() => onPage(page + 1)} disabled={page >= pages} aria-label="Next page">
                <i className="fas fa-angle-right"></i>
            </button>
            <button onClick={() => onPage(pages)} disabled={page >= pages} aria-label="Last page">
                <i className="fas fa-angle-double-right"></i>
            </button>
        </nav>
    );
}
