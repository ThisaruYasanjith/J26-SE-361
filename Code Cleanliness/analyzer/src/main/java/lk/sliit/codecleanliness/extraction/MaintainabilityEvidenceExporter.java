package lk.sliit.codecleanliness.extraction;

import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.triage.RankedIssueGroup;
import lk.sliit.codecleanliness.triage.RepositoryTriageResult;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Exports deterministic Java-analyzer evidence for downstream explanation by an LLM.
 *
 * This is an evidence export, NOT an explanation label or a verification of the
 * detector's correctness. Source files are read only from within repositoryRoot.
 */
public final class MaintainabilityEvidenceExporter {

    private static final int MAX_CONTEXT_LINES = 90;
    private static final int CONTEXT_PADDING_LINES = 6;

    public Path export(Path repositoryRoot, RepositoryTriageResult triage, Path outputFile)
            throws IOException {
        Objects.requireNonNull(repositoryRoot, "repositoryRoot");
        Objects.requireNonNull(triage, "triage");
        Objects.requireNonNull(outputFile, "outputFile");
        Path root = repositoryRoot.toRealPath();
        if (!Files.isDirectory(root)) {
            throw new IllegalArgumentException("Repository root must be a directory");
        }

        List<Object> ranked = new ArrayList<>();
        for (RankedIssueGroup entry : triage.rankedGroups()) {
            Map<String, Object> group = new LinkedHashMap<>();
            group.put("group_id", entry.group().groupId());
            group.put("rank", entry.rank());
            group.put("exceedance_score", entry.exceedanceScore());
            group.put("distinct_concern_count", entry.distinctConcernCount());
            group.put("affected_file_count", entry.affectedFileCount());
            group.put("supported_finding_count", entry.supportedFindingCount());
            group.put("ranking_explanation", entry.explanation());

            List<MaintainabilityFinding> orderedFindings = entry.group().findings().stream()
                    .sorted(Comparator.comparing(MaintainabilityFinding::findingId))
                    .toList();
            List<Object> findings = new ArrayList<>();
            for (MaintainabilityFinding finding : orderedFindings) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("finding_id", finding.findingId());
                item.put("concern", finding.concern().name());
                item.put("scope", finding.scope().name());
                item.put("symbol", finding.symbolName());
                item.put("rule_id", finding.ruleId());
                item.put("description", finding.description());
                item.put("start_line", finding.startLine());
                item.put("end_line", finding.endLine());
                item.put("evidence", new java.util.TreeMap<>(finding.evidence()));

                Path source = finding.sourceFile();
                Path candidate = (source.isAbsolute() ? source : root.resolve(source)).normalize();
                // Do not expose files outside the analyzed repository, including symlinks.
                if (!candidate.startsWith(root) || !Files.isRegularFile(candidate)
                        || !candidate.toRealPath().startsWith(root)) {
                    item.put("source_file", null);
                    item.put("code_context", null);
                    item.put("context_status", "SOURCE_UNAVAILABLE_OR_OUTSIDE_REPOSITORY");
                } else {
                    item.put("source_file", root.relativize(candidate).toString().replace('\\', '/'));
                    try {
                        List<String> lines = Files.readAllLines(candidate, StandardCharsets.UTF_8);
                        int first = Math.max(1, finding.startLine() - CONTEXT_PADDING_LINES);
                        int last = Math.min(lines.size(), finding.endLine() + CONTEXT_PADDING_LINES);
                        if (last < first) {
                            item.put("code_context", null);
                            item.put("context_status", "INVALID_SOURCE_LINE_RANGE");
                        } else {
                            boolean truncated = last - first + 1 > MAX_CONTEXT_LINES;
                            List<int[]> ranges = new ArrayList<>();
                            if (truncated) {
                                // Preserve both ends of the affected symbol rather than
                                // dropping all context for long methods/classes.
                                int frontLast = first + MAX_CONTEXT_LINES / 2 - 1;
                                int backFirst = last - (MAX_CONTEXT_LINES - MAX_CONTEXT_LINES / 2) + 1;
                                ranges.add(new int[]{first, frontLast});
                                ranges.add(new int[]{backFirst, last});
                            } else {
                                ranges.add(new int[]{first, last});
                            }

                            List<Object> segments = new ArrayList<>();
                            StringBuilder excerpt = new StringBuilder();
                            for (int[] range : ranges) {
                                Map<String, Object> segment = new LinkedHashMap<>();
                                segment.put("start_line", range[0]);
                                segment.put("end_line", range[1]);
                                StringBuilder segmentText = new StringBuilder();
                                for (int line = range[0]; line <= range[1]; line++) {
                                    String numbered = line + ": " + lines.get(line - 1);
                                    if (segmentText.length() > 0) segmentText.append('\n');
                                    segmentText.append(numbered);
                                }
                                segment.put("text", segmentText.toString());
                                segments.add(segment);
                                if (excerpt.length() > 0) {
                                    excerpt.append("\n... [middle source lines omitted] ...\n");
                                }
                                excerpt.append(segmentText);
                            }

                            Map<String, Object> context = new LinkedHashMap<>();
                            context.put("start_line", first);
                            context.put("end_line", last);
                            context.put("truncated", truncated);
                            context.put("segments", segments);
                            context.put("text", excerpt.toString());
                            item.put("code_context", context);
                            item.put("context_status", truncated
                                    ? "AVAILABLE_TRUNCATED_SOURCE_CONTEXT"
                                    : "AVAILABLE_PARTIAL_FILE_CONTEXT");
                        }
                    } catch (IOException | RuntimeException exception) {
                        item.put("code_context", null);
                        item.put("context_status", "SOURCE_READ_FAILED");
                    }
                }
                findings.add(item);
            }
            group.put("findings", findings);
            ranked.add(group);
        }

        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("schema_version", "1.1");
        payload.put("record_type", "analyzer_evidence_not_training_label");
        payload.put("analysis_scope", "repository");
        payload.put("total_files", triage.analysis().totalFiles());
        payload.put("parsed_files", triage.analysis().parsedFiles());
        payload.put("failed_files", triage.analysis().failedFiles());
        payload.put("finding_count", triage.findingCount());
        payload.put("group_count", triage.groupCount());
        payload.put("ranked_groups", ranked);
        payload.put("limitations", List.of(
                "Findings are preliminary deterministic analyzer outputs, not validated ground truth.",
                "SOLID findings indicate structural risks, not proven design-principle violations.",
                "Code excerpts are bounded and may omit middle lines; do not derive metrics not in evidence.",
                "Ranking is provisional and is not calibrated against maintenance effort."
        ));

        Path destination = outputFile.toAbsolutePath().normalize();
        Path parent = destination.getParent();
        if (parent != null) Files.createDirectories(parent);
        Files.writeString(destination, json(payload) + "\n", StandardCharsets.UTF_8);
        return destination;
    }

    /** Standard-library-only JSON serialization of the limited evidence schema. */
    private static String json(Object value) {
        if (value == null) return "null";
        if (value instanceof String text) return quote(text);
        if (value instanceof Boolean || value instanceof Integer || value instanceof Long) return value.toString();
        if (value instanceof Number number) {
            double candidate = number.doubleValue();
            return Double.isFinite(candidate) ? number.toString() : "null";
        }
        if (value instanceof Map<?, ?> map) {
            List<String> parts = new ArrayList<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                parts.add(quote(String.valueOf(entry.getKey())) + ":" + json(entry.getValue()));
            }
            return "{" + String.join(",", parts) + "}";
        }
        if (value instanceof Iterable<?> items) {
            List<String> parts = new ArrayList<>();
            for (Object item : items) parts.add(json(item));
            return "[" + String.join(",", parts) + "]";
        }
        throw new IllegalArgumentException("Unexpected JSON data type: " + value.getClass());
    }

    private static String quote(String input) {
        StringBuilder output = new StringBuilder("\"");
        for (int i = 0; i < input.length(); i++) {
            char ch = input.charAt(i);
            switch (ch) {
                case '"' -> output.append("\\\"");
                case '\\' -> output.append("\\\\");
                case '\n' -> output.append("\\n");
                case '\r' -> output.append("\\r");
                case '\t' -> output.append("\\t");
                default -> {
                    if (ch < 0x20) output.append(String.format("\\u%04x", (int) ch));
                    else output.append(ch);
                }
            }
        }
        return output.append('"').toString();
    }
}
