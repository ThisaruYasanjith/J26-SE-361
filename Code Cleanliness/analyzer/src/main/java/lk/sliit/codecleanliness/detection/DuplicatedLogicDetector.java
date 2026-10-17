
package lk.sliit.codecleanliness.detection;

import lk.sliit.codecleanliness.extraction.DuplicateCandidateFinder;
import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.model.MethodFingerprint;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/**
 * Preliminary exact normalized method-body
 * duplication detector.
 *
 * Supports same-file and cross-file duplicates.
 *
 * Findings represent duplicated-code candidates.
 * They do not prove that extracting a shared
 * abstraction would always improve maintainability.
 */
public class DuplicatedLogicDetector {

    private final DuplicateCandidateFinder candidateFinder;

    public DuplicatedLogicDetector() {
        this(new DuplicateCandidateFinder());
    }

    public DuplicatedLogicDetector(
            DuplicateCandidateFinder candidateFinder
    ) {
        this.candidateFinder = Objects.requireNonNull(
                candidateFinder,
                "Candidate finder is required"
        );
    }

    public List<MaintainabilityFinding> detect(
            RepositoryParseResult repository,
            DuplicateDetectionThresholds thresholds
    ) {
        Objects.requireNonNull(
                repository,
                "Repository parse result is required"
        );
        Objects.requireNonNull(
                thresholds,
                "Duplicate detection thresholds are required"
        );

        List<MaintainabilityFinding> findings =
                new ArrayList<>();

        List<List<MethodFingerprint>> candidates =
                candidateFinder.findCandidates(repository);

        for (List<MethodFingerprint> candidateGroup : candidates) {

            List<MethodFingerprint> members =
                    candidateGroup.stream()
                            .filter(method ->
                                    method.tokenCount()
                                            >= thresholds.minTokens())
                            .filter(method -> method.line() > 0)
                            .sorted(
                                    Comparator
                                            .comparing(
                                                    (MethodFingerprint method) ->
                                                            normalize(
                                                                    method.sourceFile()
                                                            ).toString()
                                            )
                                            .thenComparing(
                                                    MethodFingerprint::ownerType
                                            )
                                            .thenComparing(
                                                    MethodFingerprint::methodSignature
                                            )
                                            .thenComparingInt(
                                                    MethodFingerprint::line
                                            )
                            )
                            .toList();

            if (members.size() < thresholds.minOccurrences()) {
                continue;
            }

            // All occurrences must have the same
            // normalized body fingerprint.
            String fingerprint = members.get(0).fingerprint();

            if (members.stream().anyMatch(method ->
                    !fingerprint.equals(method.fingerprint()))) {
                continue;
            }

            long affectedFiles = members.stream()
                    .map(method -> normalize(method.sourceFile()))
                    .distinct()
                    .count();

            for (MethodFingerprint current : members) {

                Path sourceFile = normalize(
                        current.sourceFile()
                );

                String symbol = current.ownerType()
                        + "."
                        + current.methodSignature();

                String findingId = sourceFile
                        + ":" + current.line()
                        + ":" + symbol
                        + ":DUPLICATED_LOGIC:"
                        + fingerprint;

                String relatedOccurrences = members.stream()
                        .filter(other -> other != current)
                        .map(other ->
                                normalize(other.sourceFile())
                                + ":" + other.line()
                                + ":" + other.ownerType()
                                + "." + other.methodSignature()
                        )
                        .sorted()
                        .reduce(
                                (left, right) ->
                                        left + " | " + right
                        )
                        .orElse("");

                findings.add(new MaintainabilityFinding(
                        findingId,
                        MaintainabilityConcern.DUPLICATED_LOGIC,
                        FindingScope.METHOD,
                        sourceFile,
                        symbol,
                        current.line(),
                        current.line(),
                        "EXACT_NORMALIZED_METHOD_DUPLICATION",
                        "This method shares an identical "
                                + "normalized body fingerprint "
                                + "with other methods. "
                                + "Manual review is required "
                                + "before recommending refactoring.",
                        Map.of(
                                "fingerprint", fingerprint,
                                "normalizedTokenCount",
                                String.valueOf(current.tokenCount()),
                                "occurrenceCount",
                                String.valueOf(members.size()),
                                "affectedFileCount",
                                String.valueOf(affectedFiles),
                                "relatedOccurrences",
                                relatedOccurrences,
                                "configuredMinTokens",
                                String.valueOf(thresholds.minTokens()),
                                "configuredMinOccurrences",
                                String.valueOf(thresholds.minOccurrences()),
                                "measurement",
                                "exact_normalized_method_body"
                        )
                ));
            }
        }

        findings.sort(
                Comparator
                        .comparing(
                                (MaintainabilityFinding finding) ->
                                        finding.sourceFile().toString()
                        )
                        .thenComparingInt(
                                MaintainabilityFinding::startLine
                        )
                        .thenComparing(
                                MaintainabilityFinding::findingId
                        )
        );

        return List.copyOf(findings);
    }

    private Path normalize(Path path) {
        return path.toAbsolutePath().normalize();
    }
}
