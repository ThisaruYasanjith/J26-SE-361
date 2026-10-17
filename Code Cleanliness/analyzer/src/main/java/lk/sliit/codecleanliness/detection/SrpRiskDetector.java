
package lk.sliit.codecleanliness.detection;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;

import lk.sliit.codecleanliness.extraction.MethodUsageExtractor;
import lk.sliit.codecleanliness.model.FindingScope;
import lk.sliit.codecleanliness.model.MaintainabilityConcern;
import lk.sliit.codecleanliness.model.MaintainabilityFinding;
import lk.sliit.codecleanliness.model.MethodUsageInfo;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

/**
 * Preliminary SRP-risk candidate detector.
 *
 * Uses method-to-owned-field usage to find disconnected
 * method groups within a class.
 *
 * A candidate requires:
 * - at least four analyzable methods;
 * - at least two distinct accessed fields;
 * - at least two disconnected method groups;
 * - at least two methods per qualifying group;
 * - no unresolved references in analyzed methods.
 *
 * This is structural evidence, not proof of distinct
 * business responsibilities or an SRP violation.
 */
public class SrpRiskDetector {

    private final MethodUsageExtractor extractor =
            new MethodUsageExtractor();

    public List<MaintainabilityFinding> detect(
            RepositoryParseResult repository) {

        Objects.requireNonNull(repository);

        List<MethodUsageInfo> usages =
                extractor.extract(repository);

        Map<String, List<MethodUsageInfo>> byOwner =
                new LinkedHashMap<>();

        for (MethodUsageInfo usage : usages) {
            byOwner.computeIfAbsent(
                    usage.ownerType(),
                    ignored -> new ArrayList<>()
            ).add(usage);
        }

        List<MaintainabilityFinding> findings =
                new ArrayList<>();

        for (Map.Entry<Path, CompilationUnit> entry :
                repository.parsedFiles().entrySet()) {

            Path file = entry.getKey()
                    .toAbsolutePath().normalize();

            for (ClassOrInterfaceDeclaration type :
                    entry.getValue().findAll(
                            ClassOrInterfaceDeclaration.class)) {

                if (type.isInterface() || type.getRange().isEmpty()) {
                    continue;
                }

                String owner = type.getFullyQualifiedName()
                        .orElse(type.getNameAsString());

                List<MethodUsageInfo> methods =
                        byOwner.getOrDefault(owner, List.of())
                                .stream()
                                .filter(method ->
                                        method.sourceFile()
                                                .toAbsolutePath()
                                                .normalize()
                                                .equals(file))
                                .toList();

                if (methods.size() < 4) {
                    continue;
                }

                // Unresolved references could hide dependencies
                // between methods. Avoid a premature finding.
                if (methods.stream().anyMatch(method ->
                        !method.unresolvedReferences().isEmpty())) {
                    continue;
                }

                List<MethodUsageInfo> fieldUsingMethods =
                        methods.stream()
                                .filter(method ->
                                        !method.accessedFields().isEmpty())
                                .toList();

                if (fieldUsingMethods.size() < 4) {
                    continue;
                }

                Set<String> distinctFields = new HashSet<>();

                for (MethodUsageInfo method : fieldUsingMethods) {
                    distinctFields.addAll(method.accessedFields());
                }

                if (distinctFields.size() < 2) {
                    continue;
                }

                List<List<MethodUsageInfo>> groups =
                        connectedFieldUsageGroups(fieldUsingMethods);

                List<List<MethodUsageInfo>> qualifying =
                        groups.stream()
                                .filter(group -> group.size() >= 2)
                                .toList();

                if (qualifying.size() < 2) {
                    continue;
                }

                int start = type.getRange()
                        .orElseThrow().begin.line;

                int end = type.getRange()
                        .orElseThrow().end.line;

                String groupEvidence = qualifying.stream()
                        .map(group -> {
                            Set<String> names = new TreeSet<>();

                            for (MethodUsageInfo method : group) {
                                names.add(method.methodSignature());
                            }

                            return String.join(", ", names);
                        })
                        .toList()
                        .toString();

                findings.add(new MaintainabilityFinding(
                        file + ":" + start + ":" + owner + ":SRP_RISK",
                        MaintainabilityConcern.SRP_RISK,
                        FindingScope.CLASS,
                        file,
                        owner,
                        start,
                        end,
                        "DISCONNECTED_METHOD_FIELD_CLUSTERS",
                        "The class contains multiple substantial "
                                + "method groups using separate field "
                                + "sets. Review whether these groups "
                                + "represent distinct responsibilities.",
                        Map.of(
                                "className", owner,
                                "analyzedMethodCount",
                                String.valueOf(methods.size()),
                                "fieldUsingMethodCount",
                                String.valueOf(fieldUsingMethods.size()),
                                "distinctAccessedFields",
                                String.valueOf(distinctFields.size()),
                                "qualifyingGroupCount",
                                String.valueOf(qualifying.size()),
                                "methodGroups", groupEvidence,
                                "measurement",
                                "disconnected_owned_field_usage"
                        )
                ));
            }
        }

        findings.sort(
                Comparator.comparing(
                        (MaintainabilityFinding finding) ->
                                finding.sourceFile().toString())
                        .thenComparingInt(
                                MaintainabilityFinding::startLine)
                        .thenComparing(
                                MaintainabilityFinding::findingId)
        );

        return List.copyOf(findings);
    }

    private List<List<MethodUsageInfo>> connectedFieldUsageGroups(
            List<MethodUsageInfo> methods) {

        List<List<MethodUsageInfo>> groups =
                new ArrayList<>();

        Set<Integer> visited = new LinkedHashSet<>();

        for (int i = 0; i < methods.size(); i++) {

            if (visited.contains(i)) {
                continue;
            }

            List<Integer> pending = new ArrayList<>();
            pending.add(i);
            visited.add(i);

            List<MethodUsageInfo> group =
                    new ArrayList<>();

            for (int cursor = 0;
                 cursor < pending.size();
                 cursor++) {

                int current = pending.get(cursor);

                group.add(methods.get(current));

                for (int other = 0;
                     other < methods.size();
                     other++) {

                    if (visited.contains(other)) {
                        continue;
                    }

                    if (shareField(
                            methods.get(current),
                            methods.get(other))) {

                        visited.add(other);
                        pending.add(other);
                    }
                }
            }

            group.sort(Comparator
                    .comparingInt(MethodUsageInfo::line)
                    .thenComparing(
                            MethodUsageInfo::methodSignature));

            groups.add(group);
        }

        groups.sort(Comparator
                .comparingInt(
                        (List<MethodUsageInfo> group) ->
                                group.get(0).line())
                .thenComparing(group ->
                        group.get(0).methodSignature()));

        return groups;
    }

    private boolean shareField(
            MethodUsageInfo first,
            MethodUsageInfo second) {

        for (String field : first.accessedFields()) {
            if (second.accessedFields().contains(field)) {
                return true;
            }
        }

        return false;
    }
}
