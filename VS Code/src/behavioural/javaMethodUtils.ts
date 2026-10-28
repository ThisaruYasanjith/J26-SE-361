import * as vscode from 'vscode';

export interface ExtractedMethod {
  name: string;
  signature: string;
  fullCode: string;
  startLine: number;
  endLine: number;
}

/**
 * Robust Java method extractor that scans for method signatures and balanced braces.
 */
export class JavaMethodUtils {
  // Regex to recognize Java method declarations (with optional annotations, modifiers, generics, return type, name, params, and throws)
  private static METHOD_HEADER_REGEX = /(?:@[\w.]+(?:\([^)]*\))?\s*)*(?:public|protected|private|static|final|synchronized|abstract|default|native|\s)+[\w<>\[\],\s]+\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(([^)]*)\)\s*(?:throws\s+[\w.,\s]+)?\s*\{/g;

  /**
   * Extracts clean method code from a user selection, expanding to outer braces if needed.
   */
  public static extractFromSelectionOrCursor(
    document: vscode.TextDocument,
    selection: vscode.Selection
  ): ExtractedMethod | undefined {
    const text = document.getText();
    const selectedText = document.getText(selection).trim();

    // If the selection itself contains a complete method signature and braces
    if (selectedText.length > 0 && selectedText.includes('(') && selectedText.includes('{') && selectedText.endsWith('}')) {
      const name = this.parseMethodName(selectedText);
      const signature = this.parseSignature(selectedText);
      return {
        name: name || 'selectedMethod',
        signature: signature || name || 'method()',
        fullCode: selectedText,
        startLine: selection.start.line,
        endLine: selection.end.line,
      };
    }

    // Otherwise find the enclosing method around the cursor position
    const cursorOffset = document.offsetAt(selection.start);
    return this.findEnclosingMethodAtOffset(text, cursorOffset, document);
  }

  /**
   * Finds a method in the document by name (useful for tracking the refactored version on save).
   */
  public static findMethodByName(
    document: vscode.TextDocument,
    methodName: string
  ): ExtractedMethod | undefined {
    const text = document.getText();
    const methods = this.findAllMethods(text, document);

    // Look for exact method name match
    const match = methods.find(m => m.name === methodName);
    if (match) {
      return match;
    }

    // If only one method in file, return that
    if (methods.length === 1) {
      return methods[0];
    }

    return undefined;
  }

  /**
   * Scans document text to find all method declarations and their full bodies via balanced braces.
   */
  public static findAllMethods(
    text: string,
    document?: vscode.TextDocument
  ): ExtractedMethod[] {
    const methods: ExtractedMethod[] = [];
    const regex = new RegExp(this.METHOD_HEADER_REGEX);
    let match: RegExpExecArray | null;

    while ((match = regex.exec(text)) !== null) {
      const methodName = match[1];
      const headerStart = match.index;
      const braceOpenIndex = text.indexOf('{', headerStart);
      if (braceOpenIndex === -1) {
        continue;
      }

      const braceCloseIndex = this.findMatchingClosingBrace(text, braceOpenIndex);
      if (braceCloseIndex === -1) {
        continue;
      }

      const fullCode = text.substring(headerStart, braceCloseIndex + 1).trim();
      const signature = this.parseSignature(fullCode);

      let startLine = 0;
      let endLine = 0;
      if (document) {
        startLine = document.positionAt(headerStart).line;
        endLine = document.positionAt(braceCloseIndex).line;
      }

      methods.push({
        name: methodName,
        signature: signature || methodName,
        fullCode,
        startLine,
        endLine,
      });
    }

    return methods;
  }

  private static findEnclosingMethodAtOffset(
    text: string,
    offset: number,
    document: vscode.TextDocument
  ): ExtractedMethod | undefined {
    const methods = this.findAllMethods(text, document);
    for (const m of methods) {
      const startOffset = document.offsetAt(new vscode.Position(m.startLine, 0));
      const endOffset = document.offsetAt(new vscode.Position(m.endLine, 9999));
      if (offset >= startOffset && offset <= endOffset) {
        return m;
      }
    }

    // Fallback: if cursor is near a method or methods exist, return closest
    if (methods.length > 0) {
      let closest = methods[0];
      let minDist = Infinity;
      const cursorLine = document.positionAt(offset).line;
      for (const m of methods) {
        const dist = Math.abs(m.startLine - cursorLine);
        if (dist < minDist) {
          minDist = dist;
          closest = m;
        }
      }
      return closest;
    }

    return undefined;
  }

  private static findMatchingClosingBrace(text: string, openIndex: number): number {
    let depth = 0;
    let inString = false;
    let inChar = false;
    let inLineComment = false;
    let inBlockComment = false;

    for (let i = openIndex; i < text.length; i++) {
      const c = text[i];
      const next = i + 1 < text.length ? text[i + 1] : '';

      if (inLineComment) {
        if (c === '\n') {
          inLineComment = false;
        }
        continue;
      }
      if (inBlockComment) {
        if (c === '*' && next === '/') {
          inBlockComment = false;
          i++;
        }
        continue;
      }
      if (inString) {
        if (c === '\\') {
          i++; // escape next char
        } else if (c === '"') {
          inString = false;
        }
        continue;
      }
      if (inChar) {
        if (c === '\\') {
          i++;
        } else if (c === '\'') {
          inChar = false;
        }
        continue;
      }

      // Check comments
      if (c === '/' && next === '/') {
        inLineComment = true;
        i++;
        continue;
      }
      if (c === '/' && next === '*') {
        inBlockComment = true;
        i++;
        continue;
      }
      if (c === '"') {
        inString = true;
        continue;
      }
      if (c === '\'') {
        inChar = true;
        continue;
      }

      if (c === '{') {
        depth++;
      } else if (c === '}') {
        depth--;
        if (depth === 0) {
          return i;
        }
      }
    }

    return -1;
  }

  private static parseMethodName(code: string): string | undefined {
    const match = /([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\([^)]*\)\s*(?:throws\s+[\w.,\s]+)?\s*\{/.exec(code);
    return match ? match[1] : undefined;
  }

  private static parseSignature(code: string): string | undefined {
    const openBrace = code.indexOf('{');
    if (openBrace !== -1) {
      return code.substring(0, openBrace).replace(/\s+/g, ' ').trim();
    }
    return undefined;
  }
}
