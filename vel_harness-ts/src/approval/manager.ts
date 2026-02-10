/**
 * Parallel Approval Manager
 *
 * Handles multiple concurrent tool approval requests, enabling parallel
 * tool execution when the AI SDK requests multiple tools in the same step.
 */

import { EventEmitter } from 'events';

export interface PendingApproval {
  id: string;
  toolName: string;
  args: Record<string, unknown>;
  timestamp: number;
}

export interface ApprovalManagerEvents {
  'approval-needed': (approval: PendingApproval) => void;
  'approval-resolved': (id: string, approved: boolean) => void;
}

/**
 * Manages parallel tool approval requests.
 *
 * When the AI SDK calls multiple tool execute() functions in parallel,
 * each one may need approval. This manager:
 * 1. Tracks all pending approvals by unique ID
 * 2. Emits events when approvals are needed
 * 3. Allows external code (UI) to respond to approvals
 * 4. Resolves the waiting promises when responses come in
 *
 * Handles race conditions where:
 * - User may approve BEFORE execute() is called (pre-stored approvals)
 * - User may approve AFTER execute() is waiting (pending approvals)
 */
export class ApprovalManager extends EventEmitter {
  private pending: Map<string, {
    approval: PendingApproval;
    resolve: (approved: boolean) => void;
  }> = new Map();

  // Pre-stored approvals for when user responds before execute() is called
  private storedApprovals: Map<string, boolean> = new Map();

  private idCounter = 0;

  /**
   * Request approval for a tool call.
   * Returns a promise that resolves when the user responds.
   *
   * Checks for pre-stored approvals first (for when user approved before execute() was called).
   */
  async requestApproval(
    toolName: string,
    args: Record<string, unknown>
  ): Promise<boolean> {
    // Check if user already responded (via UI before execute() was called)
    if (this.storedApprovals.has(toolName)) {
      const approved = this.storedApprovals.get(toolName)!;
      this.storedApprovals.delete(toolName);
      return approved;
    }

    const id = `approval-${++this.idCounter}-${Date.now()}`;
    const approval: PendingApproval = {
      id,
      toolName,
      args,
      timestamp: Date.now(),
    };

    return new Promise<boolean>((resolve) => {
      this.pending.set(id, { approval, resolve });
      this.emit('approval-needed', approval);
    });
  }

  /**
   * Respond to a pending approval.
   */
  respond(id: string, approved: boolean): boolean {
    const entry = this.pending.get(id);
    if (!entry) {
      return false;
    }

    this.pending.delete(id);
    entry.resolve(approved);
    this.emit('approval-resolved', id, approved);
    return true;
  }

  /**
   * Respond to approval by tool name.
   * If the approval is already pending, resolves it.
   * If not yet pending (user responded early), stores for later.
   */
  respondByToolName(toolName: string, approved: boolean): boolean {
    // Check if there's a pending approval for this tool
    for (const [id, entry] of this.pending) {
      if (entry.approval.toolName === toolName) {
        return this.respond(id, approved);
      }
    }

    // No pending approval - user responded before execute() was called
    // Store for later
    this.storedApprovals.set(toolName, approved);
    return true;
  }

  /**
   * Get all pending approvals.
   */
  getPending(): PendingApproval[] {
    return Array.from(this.pending.values()).map((e) => e.approval);
  }

  /**
   * Get the next pending approval (FIFO).
   */
  getNext(): PendingApproval | null {
    const first = this.pending.values().next();
    if (first.done) return null;
    return first.value.approval;
  }

  /**
   * Check if there are any pending approvals.
   */
  hasPending(): boolean {
    return this.pending.size > 0;
  }

  /**
   * Get count of pending approvals.
   */
  get pendingCount(): number {
    return this.pending.size;
  }

  /**
   * Clear all pending approvals (deny all).
   */
  clear(): void {
    for (const [id, entry] of this.pending) {
      entry.resolve(false);
      this.emit('approval-resolved', id, false);
    }
    this.pending.clear();
  }
}
