package org.j26.architecture;

import com.github.javaparser.JavaParser;
import com.github.javaparser.ParseResult;
import com.github.javaparser.ParserConfiguration;
import com.github.javaparser.Problem;
import com.github.javaparser.ast.CompilationUnit;
import org.j26.architecture.model.ComponentInfo;
import org.j26.architecture.model.RelationshipInfo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public final class JavaProjectScanner {
    private static final Set<String> IGNORED_DIRECTORIES = Set.of(
            "target", "build", "out", ".git", "node_modules", "dist");

    private final JavaParser parser = new JavaParser(new ParserConfiguration()
            .setLanguageLevel(ParserConfiguration.LanguageLevel.JAVA_17)
            .setCharacterEncoding(StandardCharsets.UTF_8));
    private final ArchitectureEntityExtractor entityExtractor = new ArchitectureEntityExtractor();
    private final ArchitectureRelationshipExtractor relationshipExtractor = new ArchitectureRelationshipExtractor();

    public List<Path> discoverJavaFiles(Path projectRoot) throws IOException {
        Path root = projectRoot.toAbsolutePath().normalize();
        if (!Files.isDirectory(root)) {
            throw new IOException("Project path is not a directory: " + root);
        }

        // Prefer application sources so test fixtures and unrelated Java files stay out.
        Path mainSources = root.resolve("src/main/java");
        Path scanRoot = Files.isDirectory(mainSources) ? mainSources : root;
        List<Path> javaFiles = new ArrayList<>();

        // walkFileTree does not follow symbolic links, which avoids directory cycles.
        Files.walkFileTree(scanRoot, new SimpleFileVisitor<>() {
            @Override
            public FileVisitResult preVisitDirectory(Path directory, BasicFileAttributes attributes) {
                if (directory.getFileName() != null
                        && IGNORED_DIRECTORIES.contains(directory.getFileName().toString())) {
                    return FileVisitResult.SKIP_SUBTREE;
                }
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFile(Path file, BasicFileAttributes attributes) {
                if (attributes.isRegularFile() && file.getFileName().toString().endsWith(".java")) {
                    javaFiles.add(file);
                }
                return FileVisitResult.CONTINUE;
            }
        });

        javaFiles.sort(Comparator.comparing(Path::toString));
        return List.copyOf(javaFiles);
    }

    public ScanResult scan(Path projectRoot) throws IOException {
        List<Path> javaFiles = discoverJavaFiles(projectRoot);
        List<ParseFailure> failures = new ArrayList<>();
        List<ComponentInfo> components = new ArrayList<>();
        List<CompilationUnit> parsedUnits = new ArrayList<>();

        for (Path javaFile : javaFiles) {
            try {
                ParseResult<CompilationUnit> result = parser.parse(javaFile);
                if (!result.isSuccessful()) {
                    String message = result.getProblems().stream()
                            .map(Problem::getVerboseMessage)
                            .collect(Collectors.joining(System.lineSeparator()));
                    failures.add(new ParseFailure(javaFile, message.isBlank()
                            ? "JavaParser did not produce a compilation unit." : message));
                } else {
                    // Ignore partial ASTs from failed parses so they cannot produce misleading entities.
                    CompilationUnit unit = result.getResult().orElseThrow();
                    components.addAll(entityExtractor.extract(unit, projectRoot, javaFile));
                    parsedUnits.add(unit);
                }
            } catch (IOException exception) {
                // A file can become unreadable after discovery. Keep scanning the other files.
                failures.add(new ParseFailure(javaFile, exception.getMessage()));
            }
        }

        // Build relationships after all files are known, including types declared later in scan order.
        List<RelationshipInfo> relationships = relationshipExtractor.extract(parsedUnits, components);
        return new ScanResult(javaFiles, failures, components, relationships);
    }

    public record ParseFailure(Path filePath, String message) {
    }

    public record ScanResult(List<Path> javaFiles, List<ParseFailure> parseFailures,
                             List<ComponentInfo> components, List<RelationshipInfo> relationships) {
        public ScanResult {
            javaFiles = List.copyOf(javaFiles);
            parseFailures = List.copyOf(parseFailures);
            components = List.copyOf(components);
            relationships = List.copyOf(relationships);
        }

        public int successfullyParsed() {
            return javaFiles.size() - parseFailures.size();
        }

        public int extractedEntityCount() {
            return components.size();
        }

        public int extractedRelationshipCount() {
            return relationships.size();
        }
    }
}
