package org.j26.architecture;

import com.fasterxml.jackson.core.util.DefaultIndenter;
import com.fasterxml.jackson.core.util.DefaultPrettyPrinter;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.ObjectWriter;
import org.j26.architecture.model.ComponentInfo;
import org.j26.architecture.model.ProjectContext;
import org.j26.architecture.model.RelationshipInfo;
import org.j26.architecture.model.RelationshipType;
import org.j26.architecture.model.SourceLocation;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.InvalidPathException;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public final class ProjectContextWriter {
    private static final Comparator<RelationshipInfo> RELATIONSHIP_ORDER = Comparator
            .comparing(RelationshipInfo::source)
            .thenComparing(edge -> edge.relationship().name())
            .thenComparing(RelationshipInfo::target)
            .thenComparing(RelationshipInfo::sourceLocation, Comparator.nullsLast(
                    Comparator.comparingInt(SourceLocation::startLine).thenComparingInt(SourceLocation::endLine)));

    // Fixed indentation and LF endings keep output identical across operating systems.
    private final ObjectWriter jsonWriter = new ObjectMapper().writer(new DefaultPrettyPrinter()
            .withObjectIndenter(new DefaultIndenter("  ", "\n"))
            .withArrayIndenter(new DefaultIndenter("  ", "\n")));

    public ProjectContext createContext(Path projectRoot, List<ComponentInfo> components,
                                        List<RelationshipInfo> relationships) throws IOException {
        Path root = projectRoot.toAbsolutePath().normalize();
        if (!Files.isDirectory(root)) {
            throw new IOException("Project path is not a directory: " + root);
        }
        for (ComponentInfo component : components) {
            validateFilePath(component.filePath());
        }

        List<ComponentInfo> sortedComponents = components.stream()
                .sorted(Comparator.comparing(ComponentInfo::name).thenComparing(ComponentInfo::filePath)).toList();
        Map<RelationshipKey, RelationshipInfo> uniqueRelationships = new LinkedHashMap<>();
        // Sorting locations first makes duplicate selection independent of the input list order.
        relationships.stream().sorted(RELATIONSHIP_ORDER).forEach(edge -> uniqueRelationships.putIfAbsent(
                new RelationshipKey(edge.source(), edge.relationship(), edge.target()), edge));

        String projectName = root.getFileName() == null ? "project" : root.getFileName().toString();
        return new ProjectContext("1.0", projectName, ".", sortedComponents, List.copyOf(uniqueRelationships.values()));
    }

    public Path write(Path projectRoot, List<ComponentInfo> components,
                      List<RelationshipInfo> relationships) throws IOException {
        Path root = projectRoot.toAbsolutePath().normalize();
        ProjectContext context = createContext(root, components, relationships);
        // Finish serialization before touching the output directory or the previous context file.
        String json = jsonWriter.writeValueAsString(context) + "\n";
        Path outputDirectory = root.resolve(".architecture");
        Files.createDirectories(outputDirectory);
        Path output = outputDirectory.resolve("project_context.json");
        Path temporary = Files.createTempFile(outputDirectory, "project-context-", ".tmp");

        try {
            Files.writeString(temporary, json, StandardCharsets.UTF_8);
            // The temporary file shares the destination filesystem, allowing an atomic replacement.
            Files.move(temporary, output, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } catch (AtomicMoveNotSupportedException exception) {
            // Failing here is safer than deleting a valid context before a non-atomic replacement.
            throw new IOException("Cannot safely replace project context: this filesystem does not support atomic moves.", exception);
        } finally {
            Files.deleteIfExists(temporary);
        }

        return output;
    }

    private void validateFilePath(String value) throws IOException {
        try {
            Path path = Path.of(value);
            // Check Windows-style paths too, even when the analyzer is running on another OS.
            if (value.isBlank() || path.isAbsolute() || value.startsWith("/") || value.matches("^[A-Za-z]:.*")
                    || value.contains("\\") || path.normalize().startsWith("..")) {
                throw new IOException("Component file_path must be project-relative and use forward slashes: " + value);
            }
        } catch (InvalidPathException exception) {
            throw new IOException("Invalid component file_path: " + value, exception);
        }
    }

    private record RelationshipKey(String source, RelationshipType relationship, String target) {
    }
}
