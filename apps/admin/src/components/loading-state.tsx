export function LoadingState({ label = "Cargando..." }: { label?: string }) {
  return (
    <div className="emptyState">
      <div className="loadingSpinner"></div>
      <p>{label}</p>
    </div>
  );
}

export function LoadingSkeleton({ rows = 3, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="skeletonTable">
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div key={rowIdx} className="skeletonRow">
          {Array.from({ length: cols }).map((_, colIdx) => (
            <div key={`${rowIdx}-${colIdx}`} className="skeletonCell"></div>
          ))}
        </div>
      ))}
    </div>
  );
}
