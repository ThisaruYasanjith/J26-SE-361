package lk.sliit.codecleanliness.scanning;

import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;

public class JavaRepositoryScanner {

    private static final Set<String> DEFAULT_EXCLUSIONS = Set.of(
            ".git", "target", "build", "out", ".gradle",
            "node_modules", ".idea", "generated", "generated-sources"
    );

    private final Set<String> excludedDirectories;

    public JavaRepositoryScanner() {
        this(DEFAULT_EXCLUSIONS);
    }

    public JavaRepositoryScanner(Set<String> exclusions) {
        if (exclusions == null) {
            throw new IllegalArgumentException(
                    "Exclusion configuration cannot be null."
            );
        }

        this.excludedDirectories = exclusions.stream()
                .map(name -> name.toLowerCase(Locale.ROOT))
                .collect(java.util.stream.Collectors.toUnmodifiableSet());
    }

    public List<Path> scan(Path repositoryRoot) throws IOException {

        if (repositoryRoot == null ||
                !Files.isDirectory(repositoryRoot)) {
            throw new IllegalArgumentException(
                    "Repository root must be an existing directory."
            );
        }

        List<Path> javaFiles = new ArrayList<>();

        Files.walkFileTree(repositoryRoot, new SimpleFileVisitor<>() {

            @Override
            public FileVisitResult preVisitDirectory(
                    Path dir,
                    BasicFileAttributes attrs) {

                if (!dir.equals(repositoryRoot)) {
                    String directoryName = dir.getFileName()
                            .toString()
                            .toLowerCase(Locale.ROOT);

                    if (excludedDirectories.contains(directoryName)) {
                        return FileVisitResult.SKIP_SUBTREE;
                    }
                }

                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult visitFile(
                    Path file,
                    BasicFileAttributes attrs) {

                if (attrs.isRegularFile() &&
                        file.getFileName().toString().endsWith(".java")) {
                    javaFiles.add(file);
                }

                return FileVisitResult.CONTINUE;
            }
        });

        javaFiles.sort(Comparator.naturalOrder());

        return javaFiles;
    }
}
