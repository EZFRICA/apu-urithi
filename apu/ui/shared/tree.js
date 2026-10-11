/**
 * A knowledge, as a tree that opens and closes: the guardian's steps, the rules under each,
 * the cases decided under each rule. Both sides draw theirs with it.
 *
 * The keyboard is the WAI-ARIA tree's: Up and Down move between the parts in view, Right opens
 * a part or goes into it, Left closes it or goes back to its parent, Home and End go to the
 * first and the last, Enter chooses. One part is in the tab order at a time, so Tab leaves
 * the tree rather than walking every part. Space is left alone: on these pages it is the
 * microphone.
 *
 * A node: { id, label, tag?, state?, mark?, children?, open?, current?, extra?(li) }.
 * Every label is set as text, never as markup: it is a person's words.
 */

export class KnowledgeTree {
  constructor(root, { label, onChoose } = {}) {
    this.root = root;
    this.onChoose = onChoose || (() => {});
    this.open = new Set();
    this.focused = null;
    root.classList.add("tree");
    root.setAttribute("role", "tree");
    if (label) root.setAttribute("aria-label", label);
    root.addEventListener("keydown", (event) => this.key(event));
  }

  render(nodes) {
    this.nodes = nodes;
    for (const node of walk(nodes)) if (node.open && !this.touched) this.open.add(node.id);
    this.root.innerHTML = "";
    for (const node of nodes) this.root.appendChild(this.item(node, 1));
    const visible = this.visible();
    const target = visible.find((b) => b.dataset.id === this.focused)
      || visible.find((b) => b.getAttribute("aria-current") === "true") || visible[0];
    if (target) target.tabIndex = 0;
  }

  item(node, level) {
    const li = document.createElement("li");
    li.setAttribute("role", "none");
    const row = document.createElement("div");
    row.className = `row ${node.state || ""}`;
    const kids = node.children || [];
    const isOpen = kids.length > 0 && this.open.has(node.id);

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "toggle";
    toggle.tabIndex = -1;
    toggle.setAttribute("aria-hidden", "true");
    toggle.textContent = kids.length ? (isOpen ? "⌄" : "›") : "";
    toggle.addEventListener("click", () => this.flip(node.id));

    const button = document.createElement("button");
    button.type = "button";
    button.className = "node";
    button.tabIndex = -1;
    button.dataset.id = node.id;
    button.setAttribute("role", "treeitem");
    button.setAttribute("aria-level", String(level));
    if (kids.length) button.setAttribute("aria-expanded", String(isOpen));
    if (node.current) button.setAttribute("aria-current", "true");
    if (node.mark) {
      const mark = document.createElement("span");
      mark.className = "mark-state";
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = node.mark;
      button.appendChild(mark);
    }
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = node.label;
    button.appendChild(label);
    if (node.tag) {
      const tag = document.createElement("span");
      tag.className = "tag";
      tag.textContent = node.tag;
      button.appendChild(tag);
    }
    button.addEventListener("click", () => this.choose(node));
    button.addEventListener("focus", () => { this.focused = node.id; });
    row.append(toggle, button);
    li.appendChild(row);
    if (node.extra) node.extra(li);

    if (isOpen) {
      const group = document.createElement("ul");
      group.setAttribute("role", "group");
      for (const child of kids) group.appendChild(this.item(child, level + 1));
      li.appendChild(group);
    }
    return li;
  }

  choose(node) {
    this.focused = node.id;
    this.onChoose(node);
  }

  flip(id, force) {
    this.touched = true;
    const willOpen = force === undefined ? !this.open.has(id) : force;
    if (willOpen) this.open.add(id); else this.open.delete(id);
    this.focused = id;
    this.render(this.nodes);
    this.focus(id);
  }

  reveal(id) {
    // Opens every parent of a part, so the part chosen elsewhere is in view in the tree.
    const path = pathTo(this.nodes, id) || [];
    for (const parent of path.slice(0, -1)) this.open.add(parent.id);
  }

  visible() {
    return [...this.root.querySelectorAll("button.node")];
  }

  focus(id) {
    const buttons = this.visible();
    for (const b of buttons) b.tabIndex = -1;
    const target = buttons.find((b) => b.dataset.id === id) || buttons[0];
    if (!target) return;
    target.tabIndex = 0;
    target.focus();
  }

  key(event) {
    const buttons = this.visible();
    const at = buttons.indexOf(document.activeElement);
    if (at < 0) return;
    const current = buttons[at];
    const id = current.dataset.id;
    const node = find(this.nodes, id);
    const hasKids = (node?.children || []).length > 0;
    const go = (b) => { if (b) { event.preventDefault(); this.focus(b.dataset.id); } };
    switch (event.key) {
      case "ArrowDown": go(buttons[at + 1]); break;
      case "ArrowUp": go(buttons[at - 1]); break;
      case "Home": go(buttons[0]); break;
      case "Enter": event.preventDefault(); if (node) this.choose(node); break;
      case "End": go(buttons[buttons.length - 1]); break;
      case "ArrowRight":
        event.preventDefault();
        if (hasKids && !this.open.has(id)) this.flip(id, true);
        else if (hasKids) go(buttons[at + 1]);
        break;
      case "ArrowLeft": {
        event.preventDefault();
        if (hasKids && this.open.has(id)) { this.flip(id, false); break; }
        const parent = (pathTo(this.nodes, id) || []).slice(-2, -1)[0];
        if (parent) this.focus(parent.id);
        break;
      }
      default: return;
    }
    event.stopPropagation();
  }
}

function* walk(nodes) {
  for (const node of nodes || []) { yield node; yield* walk(node.children); }
}

function find(nodes, id) {
  for (const node of walk(nodes)) if (node.id === id) return node;
  return null;
}

function pathTo(nodes, id, trail = []) {
  for (const node of nodes || []) {
    const here = [...trail, node];
    if (node.id === id) return here;
    const deeper = pathTo(node.children, id, here);
    if (deeper) return deeper;
  }
  return null;
}
