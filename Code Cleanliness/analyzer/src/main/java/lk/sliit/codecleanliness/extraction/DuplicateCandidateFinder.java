package lk.sliit.codecleanliness.extraction;

import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.ClassOrInterfaceDeclaration;
import com.github.javaparser.ast.body.MethodDeclaration;

import lk.sliit.codecleanliness.model.MethodFingerprint;
import lk.sliit.codecleanliness.model.RepositoryParseResult;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class DuplicateCandidateFinder {

    private final JavaTokenNormalizer normalizer =
            new JavaTokenNormalizer();

    public List<List<MethodFingerprint>> findCandidates(
            RepositoryParseResult repository) {

        Map<String, List<MethodFingerprint>> index =
                new LinkedHashMap<>();

        for (Map.Entry<java.nio.file.Path, CompilationUnit> entry :
                repository.parsedFiles().entrySet()) {

            for (ClassOrInterfaceDeclaration type :
                    entry.getValue().findAll(
                            ClassOrInterfaceDeclaration.class)) {

                String owner = type.getFullyQualifiedName()
                        .orElse(type.getNameAsString());

                for (MethodDeclaration method : type.getMethods()) {

                    if (method.getBody().isEmpty()) {
                        continue;
                    }

                    List<String> tokens = normalizer.normalizeMethodBody(
                            method.getBody().orElseThrow().toString()
                    );

                    // Preliminary minimum size filter.
                    // Not a calibrated duplication-detection threshold.
                    if (tokens.size() < 10) {
                        continue;
                    }

                    String fingerprint = sha256(
                            String.join("\u001F", tokens)
                    );

                    MethodFingerprint item = new MethodFingerprint(
                            entry.getKey(),
                            owner,
                            method.getSignature().asString(),
                            method.getBegin()
                                    .map(p -> p.line)
                                    .orElse(-1),
                            tokens.size(),
                            fingerprint
                    );

                    index.computeIfAbsent(
                            fingerprint,
                            ignored -> new ArrayList<>()
                    ).add(item);
                }
            }
        }

        return index.values().stream()
                .filter(group -> group.size() > 1)
                .map(List::copyOf)
                .toList();
    }

    private String sha256(String input) {

        try {
            MessageDigest digest =
                    MessageDigest.getInstance("SHA-256");

            byte[] bytes = digest.digest(
                    input.getBytes(StandardCharsets.UTF_8)
            );

            return HexFormat.of().formatHex(bytes);

        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 is unavailable", ex
            );
        }
    }
}