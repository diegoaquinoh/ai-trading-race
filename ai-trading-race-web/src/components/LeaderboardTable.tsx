import { Link } from "react-router-dom";
import type { LeaderboardEntry } from "../types";
import "./LeaderboardTable.css";

/** Maps backend ModelProvider enum strings to user-friendly display names */
function getModelDisplayName(modelType: string, agentName: string): string {
  switch (modelType) {
    case "AzureOpenAI":
      return agentName; // Each Azure OpenAI agent has its own model name
    case "Llama":
      return "Llama";
    case "CustomML":
      return "ML Agent";
    case "Mock":
      return "Test";
    default:
      return modelType;
  }
}

/** Returns a CSS-safe class name for the model badge */
function getModelBadgeClass(modelType: string): string {
  switch (modelType) {
    case "AzureOpenAI":
      return "azureopenai";
    case "CustomML":
      return "customml";
    case "Mock":
      return "mock";
    case "Llama":
      return "llama";
    default:
      return modelType.toLowerCase();
  }
}

interface LeaderboardTableProps {
  entries: LeaderboardEntry[];
  onSort?: (column: string) => void;
  sortColumn?: string;
  sortDirection?: "asc" | "desc";
}

export function LeaderboardTable({
  entries,
  onSort,
  sortColumn,
  sortDirection,
}: LeaderboardTableProps) {
  const handleSort = (column: string) => {
    if (onSort) {
      onSort(column);
    }
  };

  const getSortIcon = (column: string) => {
    if (sortColumn !== column) return <i className="fas fa-sort"></i>;
    return sortDirection === "asc" ? <i className="fas fa-sort-up"></i> : <i className="fas fa-sort-down"></i>;
  };

  return (
    <div className="leaderboard-container">
      <table className="leaderboard-table">
        <thead>
          <tr>
            <th className="col-rank">#</th>
            <th className="col-agent">Agent</th>
            <th className="col-type">Model</th>
            <th
              className="col-value sortable"
              onClick={() => handleSort("value")}
            >
              Value{" "}
              {onSort && (
                <span className="sort-icon">{getSortIcon("value")}</span>
              )}
            </th>
            <th
              className="col-performance sortable"
              onClick={() => handleSort("performance")}
            >
              Performance{" "}
              {onSort && (
                <span className="sort-icon">{getSortIcon("performance")}</span>
              )}
            </th>
            <th className="col-drawdown">Drawdown</th>
          </tr>
        </thead>
        <tbody>
          {entries.map((entry, index) => (
            <tr key={entry.agent.id} className="leaderboard-row">
              <td className="rank">
                <span className={`rank-badge rank-${index + 1}`}>
                  {index + 1}
                </span>
              </td>
              <td className="agent-cell">
                <Link to={`/agents/${entry.agent.id}`} className="agent-link">
                  <span className="agent-name">{entry.agent.name}</span>
                  <span className="agent-provider">{entry.agent.provider}</span>
                </Link>
              </td>
              <td>
                <span
                  className={`badge ${getModelBadgeClass(entry.agent.modelType)}`}
                >
                  {getModelDisplayName(entry.agent.modelType, entry.agent.name)}
                </span>
              </td>
              <td className="value">
                $
                {entry.currentValue.toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </td>
              <td
                className={
                  entry.performancePercent >= 0 ? "positive" : "negative"
                }
              >
                <span className="performance-value">
                  {entry.performancePercent >= 0 ? "+" : ""}
                  {entry.performancePercent.toFixed(2)}%
                </span>
              </td>
              <td className="drawdown negative">
                {entry.drawdown.toFixed(2)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {entries.length === 0 && (
        <div className="leaderboard-empty">No agents found</div>
      )}
    </div>
  );
}
