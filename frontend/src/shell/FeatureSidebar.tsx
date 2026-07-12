import { useEffect, useMemo, useState } from "react";

type AppNode = { type: "app"; feature: string; label?: string };
type FolderNode = { type: "folder"; id: string; label: string; children: AppNode[] };
type MenuNode = AppNode | FolderNode;

interface Props {
  projectId: string;
  features: string[];
  titleOf: (feature: string) => string;
  iconOf: (feature: string) => string;
  activeFeature: string | null;
  onOpen: (feature: string) => void;
  lockedFeatures?: Set<string>;
}

const appNode = (feature: string): AppNode => ({ type: "app", feature });

function storageKey(projectId: string) {
  return `af_feature_navigation:${projectId}`;
}

function normalize(nodes: MenuNode[], features: string[]): MenuNode[] {
  const allowed = new Set(features);
  const seen = new Set<string>();
  const next: MenuNode[] = [];
  for (const node of nodes) {
    if (node.type === "app") {
      if (allowed.has(node.feature) && !seen.has(node.feature)) {
        next.push(node);
        seen.add(node.feature);
      }
      continue;
    }
    const children = node.children.filter((child) => allowed.has(child.feature) && !seen.has(child.feature));
    children.forEach((child) => seen.add(child.feature));
    if (children.length >= 2) next.push({ ...node, children });
    else if (children.length === 1) next.push(children[0]);
  }
  features.forEach((feature) => {
    if (!seen.has(feature)) next.push(appNode(feature));
  });
  return next;
}

function load(projectId: string, features: string[]): MenuNode[] {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey(projectId)) || "[]") as MenuNode[];
    return normalize(Array.isArray(value) ? value : [], features);
  } catch {
    return features.map(appNode);
  }
}

function removeNode(nodes: MenuNode[], dragId: string): { nodes: MenuNode[]; removed: MenuNode | null } {
  let removed: MenuNode | null = null;
  const next: MenuNode[] = [];
  for (const node of nodes) {
    if ((node.type === "app" ? `app:${node.feature}` : `folder:${node.id}`) === dragId) {
      removed = node;
      continue;
    }
    if (node.type === "folder") {
      const children = node.children.filter((child) => {
        if (`app:${child.feature}` !== dragId) return true;
        removed = child;
        return false;
      });
      next.push({ ...node, children });
    } else next.push(node);
  }
  return { nodes: next, removed };
}

function insertBeside(nodes: MenuNode[], targetFeature: string, value: MenuNode, after: boolean): MenuNode[] {
  const next: MenuNode[] = [];
  for (const node of nodes) {
    if (node.type === "app" && node.feature === targetFeature) {
      if (!after) next.push(value);
      next.push(node);
      if (after) next.push(value);
    } else if (node.type === "folder" && node.children.some((child) => child.feature === targetFeature)) {
      if (value.type !== "app") {
        next.push(node);
        continue;
      }
      const children: AppNode[] = [];
      node.children.forEach((child) => {
        if (child.feature === targetFeature && !after) children.push(value);
        children.push(child);
        if (child.feature === targetFeature && after) children.push(value);
      });
      next.push({ ...node, children });
    } else next.push(node);
  }
  return next;
}

function mergeOn(nodes: MenuNode[], targetFeature: string, value: MenuNode, titleOf: (feature: string) => string): MenuNode[] {
  if (value.type !== "app") return nodes;
  return nodes.map((node) => {
    if (node.type === "folder" && node.children.some((child) => child.feature === targetFeature)) {
      return { ...node, children: [...node.children, value] };
    }
    if (node.type === "app" && node.feature === targetFeature) {
      return {
        type: "folder",
        id: `folder_${Date.now().toString(36)}`,
        label: `${titleOf(targetFeature)} フォルダ`,
        children: [node, value],
      };
    }
    return node;
  });
}

export function FeatureSidebar({ projectId, features, titleOf, iconOf, activeFeature, onOpen, lockedFeatures = new Set() }: Props) {
  const featureSignature = features.join("\u0000");
  const [nodes, setNodes] = useState<MenuNode[]>(() => load(projectId, features));
  const [dragId, setDragId] = useState<string | null>(null);
  const [openFolders, setOpenFolders] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setNodes((current) => normalize(current, features));
  }, [featureSignature]);
  useEffect(() => {
    localStorage.setItem(storageKey(projectId), JSON.stringify(nodes));
  }, [nodes, projectId]);

  const featureLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    const visit = (node: MenuNode) => {
      if (node.type === "app") labels[node.feature] = node.label || titleOf(node.feature);
      else node.children.forEach(visit);
    };
    nodes.forEach(visit);
    return labels;
  }, [nodes, titleOf]);

  function commit(raw: MenuNode[]) {
    setNodes(normalize(raw, features));
  }

  function dropOnApp(event: React.DragEvent, targetFeature: string) {
    event.preventDefault();
    event.stopPropagation();
    if (!dragId || dragId === `app:${targetFeature}`) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientY - rect.top) / Math.max(1, rect.height);
    const removed = removeNode(nodes, dragId);
    if (!removed.removed) return;
    let next = removed.nodes;
    if (ratio >= 0.25 && ratio <= 0.75) next = mergeOn(next, targetFeature, removed.removed, titleOf);
    else next = insertBeside(next, targetFeature, removed.removed, ratio > 0.5);
    commit(next);
    setDragId(null);
  }

  function dropOnFolder(event: React.DragEvent, folderId: string) {
    event.preventDefault();
    event.stopPropagation();
    if (!dragId) return;
    const removed = removeNode(nodes, dragId);
    if (!removed.removed || removed.removed.type !== "app") return;
    commit(removed.nodes.map((node) => node.type === "folder" && node.id === folderId
      ? { ...node, children: [...node.children, removed.removed as AppNode] }
      : node));
    setOpenFolders((current) => new Set(current).add(folderId));
    setDragId(null);
  }

  function dropAtRoot(event: React.DragEvent) {
    event.preventDefault();
    event.stopPropagation();
    if (!dragId) return;
    const removed = removeNode(nodes, dragId);
    if (removed.removed) commit([...removed.nodes, removed.removed]);
    setDragId(null);
  }

  function renameApp(event: React.MouseEvent, feature: string) {
    event.preventDefault();
    const label = window.prompt("アプリ名を変更", featureLabels[feature] || titleOf(feature));
    if (!label?.trim()) return;
    setNodes((current) => current.map((node) => node.type === "app"
      ? (node.feature === feature ? { ...node, label: label.trim() } : node)
      : { ...node, children: node.children.map((child) => child.feature === feature ? { ...child, label: label.trim() } : child) }));
  }

  function renameFolder(event: React.MouseEvent, folderId: string, currentLabel: string) {
    event.preventDefault();
    const label = window.prompt("フォルダ名を変更", currentLabel);
    if (!label?.trim()) return;
    setNodes((current) => current.map((node) => node.type === "folder" && node.id === folderId
      ? { ...node, label: label.trim() }
      : node));
  }

  return (
    <div className="feature-tree" onDragOver={(event) => event.preventDefault()} onDrop={dropAtRoot} data-testid="feature-tree">
      {nodes.map((node) => node.type === "app" ? (
        <button
          key={node.feature}
          className={`${activeFeature === node.feature ? "navitem navitem--active" : "navitem"} feature-tree__app${lockedFeatures.has(node.feature) ? " feature-tree__app--locked" : ""}`}
          disabled={lockedFeatures.has(node.feature)}
          title={lockedFeatures.has(node.feature) ? "改修中です。進捗はメインチャットで確認できます。" : undefined}
          draggable
          data-feature={node.feature}
          onDragStart={() => setDragId(`app:${node.feature}`)}
          onDragEnd={() => setDragId(null)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => dropOnApp(event, node.feature)}
          onContextMenu={(event) => renameApp(event, node.feature)}
          onClick={() => onOpen(node.feature)}
        >
          {iconOf(node.feature)} {node.label || titleOf(node.feature)}
        </button>
      ) : (
        <div
          key={node.id}
          className="feature-tree__folder"
          draggable
          data-folder={node.id}
          onDragStart={() => setDragId(`folder:${node.id}`)}
          onDragEnd={() => setDragId(null)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => dropOnFolder(event, node.id)}
        >
          <button
            className="navitem feature-tree__folder-button"
            aria-expanded={openFolders.has(node.id)}
            onContextMenu={(event) => renameFolder(event, node.id, node.label)}
            onClick={() => setOpenFolders((current) => {
              const next = new Set(current);
              if (next.has(node.id)) next.delete(node.id); else next.add(node.id);
              return next;
            })}
          >
            <span>{openFolders.has(node.id) ? "▾" : "▸"} 📁 {node.label}</span>
            <span className="feature-tree__count">{node.children.length}</span>
          </button>
          {openFolders.has(node.id) && (
            <div className="feature-tree__children">
              {node.children.map((child) => (
                <button
                  key={child.feature}
                  className={`${activeFeature === child.feature ? "navitem navitem--active" : "navitem"} feature-tree__app${lockedFeatures.has(child.feature) ? " feature-tree__app--locked" : ""}`}
                  disabled={lockedFeatures.has(child.feature)}
                  title={lockedFeatures.has(child.feature) ? "改修中です。進捗はメインチャットで確認できます。" : undefined}
                  draggable
                  data-feature={child.feature}
                  onDragStart={(event) => { event.stopPropagation(); setDragId(`app:${child.feature}`); }}
                  onDragEnd={() => setDragId(null)}
                  onDragOver={(event) => event.preventDefault()}
                  onDrop={(event) => dropOnApp(event, child.feature)}
                  onContextMenu={(event) => renameApp(event, child.feature)}
                  onClick={() => onOpen(child.feature)}
                >
                  {iconOf(child.feature)} {child.label || titleOf(child.feature)}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
