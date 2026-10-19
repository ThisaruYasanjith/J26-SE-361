package org.j26.architecture;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.j26.architecture.model.ComponentInfo;
import org.j26.architecture.model.EntityType;
import org.j26.architecture.model.ProjectContext;
import org.j26.architecture.model.RelationshipInfo;
import org.j26.architecture.model.RelationshipType;
import org.j26.architecture.model.SourceLocation;
import org.j26.architecture.model.SpringType;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ProjectContextWriterTest {
    @TempDir
    Path project;

    private final ProjectContextWriter writer = new ProjectContextWriter();
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void createsTheOutputDirectoryAndContextInsideTheAnalyzedProject() throws IOException {
        assertFalse(Files.exists(project.resolve(".architecture")));

        Path output = writer.write(project, List.of(component("demo.Source")), List.of());

        assertEquals(project.resolve(".architecture/project_context.json"), output);
        assertTrue(Files.isDirectory(project.resolve(".architecture")));
        assertTrue(Files.isRegularFile(output));
        assertFalse(Files.exists(project.resolve("project_context.json")));
        assertEquals(1, mapper.readTree(output.toFile()).get("components").size());
    }

    @Test
    void assemblesTheVersionFolderNameAndPortableRoot() throws IOException {
        Path root = Files.createDirectories(project.resolve("payments/unused/.."));
        ProjectContext context = writer.createContext(root, List.of(), List.of());

        assertEquals("1.0", context.schemaVersion());
        assertEquals("payments", context.projectName());
        assertEquals(".", context.projectRoot());
        assertFalse(Files.exists(root.resolve(".architecture")));
    }

    @Test
    void writesOnlyTheRequiredContextAndComponentFields() throws IOException {
        ComponentInfo service = new ComponentInfo("demo.PaymentService", EntityType.CLASS, SpringType.SERVICE,
                "demo", "src/main/java/demo/PaymentService.java", List.of("Service", "Deprecated"),
                new SourceLocation(3, 8), "BaseService", List.of("Auditable"), List.of());

        JsonNode json = mapper.readTree(writer.write(project, List.of(service), List.of()).toFile());
        JsonNode component = json.get("components").get(0);

        assertEquals(Set.of("schema_version", "project_name", "project_root", "components", "relationships"), fields(json));
        assertEquals("1.0", json.get("schema_version").asText());
        assertEquals(project.getFileName().toString(), json.get("project_name").asText());
        assertEquals(".", json.get("project_root").asText());
        assertEquals(Set.of("name", "entity_type", "spring_type", "package", "file_path", "annotations", "source_location"), fields(component));
        assertEquals("demo.PaymentService", component.get("name").asText());
        assertEquals("CLASS", component.get("entity_type").asText());
        assertEquals("SERVICE", component.get("spring_type").asText());
        assertEquals("demo", component.get("package").asText());
        assertEquals("src/main/java/demo/PaymentService.java", component.get("file_path").asText());
        assertEquals(List.of("Service", "Deprecated"), mapper.convertValue(component.get("annotations"), List.class));
        assertEquals(Set.of("start_line", "end_line"), fields(component.get("source_location")));
        assertEquals(3, component.get("source_location").get("start_line").asInt());
        assertEquals(8, component.get("source_location").get("end_line").asInt());
    }

    @Test
    void writesRelationshipFieldsAndOmitsUnknownLocations() throws IOException {
        List<RelationshipInfo> edges = List.of(
                new RelationshipInfo("demo.Source", "demo.Target", RelationshipType.DEPENDS_ON, new SourceLocation(4, 5)),
                new RelationshipInfo("demo.Source", "demo.Target", RelationshipType.CALLS, null));

        JsonNode relationships = mapper.readTree(writer.write(project,
                List.of(component("demo.Source"), component("demo.Target")), edges).toFile()).get("relationships");

        assertEquals(2, relationships.size());
        assertEquals(Set.of("source", "target", "relationship"), fields(relationships.get(0)));
        JsonNode dependency = relationships.get(1);
        assertEquals(Set.of("source", "target", "relationship", "source_location"), fields(dependency));
        assertEquals("demo.Source", dependency.get("source").asText());
        assertEquals("demo.Target", dependency.get("target").asText());
        assertEquals("DEPENDS_ON", dependency.get("relationship").asText());
        assertEquals(4, dependency.get("source_location").get("start_line").asInt());
        assertEquals(5, dependency.get("source_location").get("end_line").asInt());
    }

    @Test
    void sortsComponentsByFullyQualifiedName() throws IOException {
        ProjectContext context = writer.createContext(project,
                List.of(component("zebra.Source"), component("alpha.Target"), component("alpha.Source")), List.of());

        assertEquals(List.of("alpha.Source", "alpha.Target", "zebra.Source"),
                context.components().stream().map(ComponentInfo::name).toList());
    }

    @Test
    void sortsRelationshipsAndDeduplicatesUsingTheFirstKnownLocation() throws IOException {
        List<RelationshipInfo> edges = List.of(
                new RelationshipInfo("demo.Z", "demo.A", RelationshipType.DEPENDS_ON, null),
                new RelationshipInfo("demo.A", "demo.C", RelationshipType.DEPENDS_ON, null),
                new RelationshipInfo("demo.A", "demo.C", RelationshipType.IMPORTS, null),
                new RelationshipInfo("demo.A", "demo.B", RelationshipType.DEPENDS_ON, new SourceLocation(9, 9)),
                new RelationshipInfo("demo.A", "demo.B", RelationshipType.DEPENDS_ON, null),
                new RelationshipInfo("demo.A", "demo.B", RelationshipType.CALLS, null),
                new RelationshipInfo("demo.A", "demo.B", RelationshipType.DEPENDS_ON, new SourceLocation(3, 4)));

        ProjectContext context = writer.createContext(project, List.of(), edges);

        assertEquals(List.of("demo.A CALLS demo.B", "demo.A DEPENDS_ON demo.B", "demo.A DEPENDS_ON demo.C",
                "demo.A IMPORTS demo.C", "demo.Z DEPENDS_ON demo.A"),
                context.relationships().stream().map(this::signature).toList());
        assertEquals(new SourceLocation(3, 4), context.relationships().get(1).sourceLocation());
    }

    @Test
    void repeatedGenerationAndInputReorderingProduceIdenticalBytes() throws IOException {
        List<ComponentInfo> components = new ArrayList<>(List.of(component("demo.Z"), component("demo.A")));
        List<RelationshipInfo> edges = new ArrayList<>(List.of(
                new RelationshipInfo("demo.Z", "demo.A", RelationshipType.DEPENDS_ON, null),
                new RelationshipInfo("demo.Z", "demo.A", RelationshipType.CALLS, new SourceLocation(2, 2)),
                new RelationshipInfo("demo.Z", "demo.A", RelationshipType.DEPENDS_ON, new SourceLocation(3, 3))));
        Path output = writer.write(project, components, edges);
        byte[] original = Files.readAllBytes(output);

        writer.write(project, components, edges);
        assertArrayEquals(original, Files.readAllBytes(output));
        Collections.reverse(components);
        Collections.reverse(edges);
        writer.write(project, components, edges);
        assertArrayEquals(original, Files.readAllBytes(output));
    }

    @Test
    void outputIsPortableAcrossDifferentMachineRootPaths() throws IOException {
        Path firstRoot = Files.createDirectories(project.resolve("machine-one/payments"));
        Path secondRoot = Files.createDirectories(project.resolve("machine-two/payments"));
        List<ComponentInfo> components = List.of(component("demo.Source"));

        byte[] first = Files.readAllBytes(writer.write(firstRoot, components, List.of()));
        byte[] second = Files.readAllBytes(writer.write(secondRoot, components, List.of()));

        assertArrayEquals(first, second);
        String json = new String(first, StandardCharsets.UTF_8);
        assertFalse(json.contains("machine-one"));
        assertFalse(json.contains("machine-two"));
        assertFalse(json.contains(project.toString().replace('\\', '/')));
        assertFalse(json.contains(project.toString().replace("\\", "\\\\")));
    }

    @Test
    void writesPrettyUtf8JsonWithFixedLineEndings() throws IOException {
        Path unicodeRoot = Files.createDirectories(project.resolve("paiements-é"));

        Path output = writer.write(unicodeRoot, List.of(component("demo.Source")), List.of());
        String json = Files.readString(output, StandardCharsets.UTF_8);

        assertTrue(json.contains("paiements-é"));
        assertTrue(json.contains("\n  \"schema_version\""));
        assertTrue(json.endsWith("\n"));
        assertFalse(json.contains("\r"));
        assertEquals("paiements-é", mapper.readTree(json).get("project_name").asText());
    }

    @Test
    void replacesAnExistingContextAndLeavesNoTemporaryFiles() throws IOException {
        Path output = writer.write(project, List.of(component("demo.Before")), List.of());

        writer.write(project, List.of(component("demo.After")), List.of());

        assertEquals("demo.After", mapper.readTree(output.toFile()).get("components").get(0).get("name").asText());
        try (var files = Files.list(output.getParent())) {
            assertEquals(List.of("project_context.json"), files.map(file -> file.getFileName().toString()).toList());
        }
    }

    @ParameterizedTest
    @ValueSource(strings = {"C:/private/Source.java", "/private/Source.java", "../Source.java", "src/../../Source.java", "src\\Source.java"})
    void rejectsNonPortableFilePathsWithoutReplacingAnExistingContext(String filePath) throws IOException {
        Path output = writer.write(project, List.of(component("demo.Before")), List.of());
        byte[] previous = Files.readAllBytes(output);
        ComponentInfo badPath = new ComponentInfo("demo.Source", EntityType.CLASS, SpringType.NONE, "demo", filePath,
                List.of(), new SourceLocation(1, 1), null, List.of(), List.of());

        IOException error = assertThrows(IOException.class, () -> writer.write(project, List.of(badPath), List.of()));

        assertTrue(error.getMessage().contains("project-relative"));
        assertArrayEquals(previous, Files.readAllBytes(output));
    }

    @Test
    void reportsBlockedOutputDirectories() throws IOException {
        Files.writeString(project.resolve(".architecture"), "This file blocks directory creation.");

        assertThrows(IOException.class, () -> writer.write(project, List.of(), List.of()));

        assertEquals("This file blocks directory creation.", Files.readString(project.resolve(".architecture")));
    }

    @Test
    void cleansTemporaryFilesWhenReplacementFails() throws IOException {
        Path occupied = Files.createDirectories(project.resolve(".architecture/project_context.json"));
        Files.writeString(occupied.resolve("keep.txt"), "Keep this existing entry.");

        assertThrows(IOException.class, () -> writer.write(project, List.of(), List.of()));

        assertEquals("Keep this existing entry.", Files.readString(occupied.resolve("keep.txt")));
        try (var files = Files.list(occupied.getParent())) {
            assertEquals(List.of("project_context.json"), files.map(file -> file.getFileName().toString()).toList());
        }
    }

    @Test
    void rejectsMissingOrNonDirectoryProjectRoots() throws IOException {
        Path file = Files.writeString(project.resolve("not-a-project.txt"), "text");

        assertThrows(IOException.class, () -> writer.write(project.resolve("missing"), List.of(), List.of()));
        assertThrows(IOException.class, () -> writer.write(file, List.of(), List.of()));
        assertFalse(Files.exists(project.resolve("missing")));
    }

    @Test
    void cliReportsWriteFailuresWithANonzeroStatusAndKeepsTheScanSummary() throws IOException {
        writeSource("demo/Source.java", "package demo; class Source {}");
        Files.writeString(project.resolve(".architecture"), "Blocked");
        ByteArrayOutputStream summary = new ByteArrayOutputStream();
        ByteArrayOutputStream errors = new ByteArrayOutputStream();

        try (PrintStream output = new PrintStream(summary, true, StandardCharsets.UTF_8);
             PrintStream errorOutput = new PrintStream(errors, true, StandardCharsets.UTF_8)) {
            assertEquals(1, AnalyzerMain.run(new String[]{project.toString()}, output, errorOutput));
        }

        assertTrue(summary.toString(StandardCharsets.UTF_8).contains("Java files found: 1"));
        assertFalse(summary.toString(StandardCharsets.UTF_8).contains("Project context written to:"));
        assertTrue(errors.toString(StandardCharsets.UTF_8).contains("Error: unable to write project context:"));
    }

    @Test
    void cliWritesTheSevenEntityResearchFixtureAndPreservesItsMetadata() throws IOException {
        writeResearchFixture();
        ByteArrayOutputStream summary = new ByteArrayOutputStream();
        ByteArrayOutputStream errors = new ByteArrayOutputStream();

        try (PrintStream output = new PrintStream(summary, true, StandardCharsets.UTF_8);
             PrintStream errorOutput = new PrintStream(errors, true, StandardCharsets.UTF_8)) {
            assertEquals(0, AnalyzerMain.run(new String[]{project.toString()}, output, errorOutput));
        }

        Path output = project.resolve(".architecture/project_context.json");
        JsonNode json = mapper.readTree(output.toFile());
        Map<String, JsonNode> entities = new java.util.LinkedHashMap<>();
        json.get("components").forEach(component -> entities.put(component.get("name").asText(), component));
        assertEquals(7, entities.size());
        assertEquals("CONTROLLER", entities.get("demo.controller.PaymentController").get("spring_type").asText());
        assertEquals("SERVICE", entities.get("demo.service.PaymentService").get("spring_type").asText());
        assertEquals("REPOSITORY", entities.get("demo.repository.PaymentRepository").get("spring_type").asText());
        assertEquals("INTERFACE", entities.get("demo.repository.PaymentRepository").get("entity_type").asText());
        assertEquals("SERVICE", entities.get("demo.service.ReportingService").get("spring_type").asText());
        JsonNode misplaced = entities.get("demo.controller.MisplacedAuditService");
        assertEquals("SERVICE", misplaced.get("spring_type").asText());
        assertEquals("demo.controller", misplaced.get("package").asText());
        assertEquals("src/main/java/demo/controller/MisplacedAuditService.java", misplaced.get("file_path").asText());

        Set<String> edges = new HashSet<>();
        json.get("relationships").forEach(edge -> edges.add(edge.get("source").asText() + " "
                + edge.get("relationship").asText() + " " + edge.get("target").asText()));
        assertTrue(edges.containsAll(Set.of(
                "demo.controller.PaymentController DEPENDS_ON demo.service.PaymentService",
                "demo.service.PaymentService DEPENDS_ON demo.repository.PaymentRepository",
                "demo.service.PaymentService DEPENDS_ON demo.gateway.PaymentGateway",
                "demo.service.ReportingService DEPENDS_ON demo.gateway.PaymentGateway",
                "demo.controller.AdminController DEPENDS_ON demo.repository.PaymentRepository")));
        assertEquals(json.get("relationships").size(), edges.size());
        assertTrue(json.get("relationships").size() > 0);
        assertTrue(summary.toString(StandardCharsets.UTF_8).contains("Architecture entities extracted: 7"));
        assertTrue(summary.toString(StandardCharsets.UTF_8).contains("Project context written to:\n.architecture/project_context.json")
                || summary.toString(StandardCharsets.UTF_8).contains("Project context written to:\r\n.architecture/project_context.json"));
        assertEquals("", errors.toString(StandardCharsets.UTF_8));
    }

    @Test
    void partialScansStillWriteSuccessfulEntitiesAndReturnFailure() throws IOException {
        writeSource("demo/ABroken.java", "package demo; class ABroken { void broken( }");
        writeSource("demo/Valid.java", "package demo; class Valid {}");
        ByteArrayOutputStream messages = new ByteArrayOutputStream();

        try (PrintStream output = new PrintStream(messages, true, StandardCharsets.UTF_8)) {
            assertEquals(1, AnalyzerMain.run(new String[]{project.toString()}, output, output));
        }

        JsonNode json = mapper.readTree(project.resolve(".architecture/project_context.json").toFile());
        assertEquals(1, json.get("components").size());
        assertEquals("demo.Valid", json.get("components").get(0).get("name").asText());
        assertTrue(messages.toString(StandardCharsets.UTF_8).contains("Parse failures: 1"));
    }

    @Test
    void emptyProjectsProduceValidEmptyArrays() throws IOException {
        JsonNode json = mapper.readTree(writer.write(project, List.of(), List.of()).toFile());

        assertTrue(json.get("components").isArray());
        assertEquals(0, json.get("components").size());
        assertTrue(json.get("relationships").isArray());
        assertEquals(0, json.get("relationships").size());
    }

    private void writeResearchFixture() throws IOException {
        writeSource("demo/repository/PaymentRepository.java", "package demo.repository; @Repository public interface PaymentRepository {}");
        writeSource("demo/gateway/PaymentGateway.java", "package demo.gateway; public interface PaymentGateway {}");
        writeSource("demo/service/PaymentService.java", """
                package demo.service;
                import demo.repository.PaymentRepository;
                import demo.gateway.PaymentGateway;
                @Service class PaymentService {
                    PaymentRepository repository;
                    PaymentGateway gateway;
                    PaymentService(PaymentRepository repository, PaymentGateway gateway) {}
                    void pay() { repository.save(); gateway.charge(); }
                }
                """);
        writeSource("demo/service/ReportingService.java", """
                package demo.service;
                import demo.gateway.PaymentGateway;
                @Service class ReportingService {
                    ReportingService(PaymentGateway gateway) { gateway.charge(); }
                }
                """);
        writeSource("demo/controller/PaymentController.java", """
                package demo.controller;
                import demo.service.PaymentService;
                @RestController class PaymentController { PaymentService service; void pay() { service.pay(); } }
                """);
        writeSource("demo/controller/AdminController.java", """
                package demo.controller;
                import demo.repository.PaymentRepository;
                @RestController class AdminController { PaymentRepository repository; void report() { repository.findAll(); } }
                """);
        writeSource("demo/controller/MisplacedAuditService.java", "package demo.controller; @Service class MisplacedAuditService {}");
    }

    private void writeSource(String relativePath, String source) throws IOException {
        Path file = project.resolve("src/main/java").resolve(relativePath);
        Files.createDirectories(file.getParent());
        Files.writeString(file, source, StandardCharsets.UTF_8);
    }

    private ComponentInfo component(String name) {
        String packageName = name.substring(0, name.lastIndexOf('.'));
        return new ComponentInfo(name, EntityType.CLASS, SpringType.NONE, packageName,
                "src/main/java/" + name.replace('.', '/') + ".java", List.of(), new SourceLocation(1, 1),
                null, List.of(), List.of());
    }

    private Set<String> fields(JsonNode node) {
        Set<String> fields = new HashSet<>();
        node.fieldNames().forEachRemaining(fields::add);
        return fields;
    }

    private String signature(RelationshipInfo edge) {
        return edge.source() + " " + edge.relationship() + " " + edge.target();
    }
}
