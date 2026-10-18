package lk.sliit.codecleanliness.analysis;

import lk.sliit.codecleanliness.detection.ClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.CohesionDetectionThresholds;
import lk.sliit.codecleanliness.detection.DuplicateDetectionThresholds;
import lk.sliit.codecleanliness.detection.GodClassDetectionThresholds;
import lk.sliit.codecleanliness.detection.MethodDetectionThresholds;
import lk.sliit.codecleanliness.detection.NamingDetectionConfig;
import lk.sliit.codecleanliness.extraction.MaintainabilityEvidenceExporter;
import lk.sliit.codecleanliness.triage.RepositoryTriageResult;
import lk.sliit.codecleanliness.triage.RepositoryTriageService;

import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Command-line entry point for an evidence-only maintainability triage export.
 *
 * The configuration below is an explicit preliminary demonstration profile.
 * It is NOT an empirically calibrated smell-detection threshold set.
 * The generated report is NOT ground truth or a supervised training label.
 */
public final class MaintainabilityTriageCli {

    private MaintainabilityTriageCli() {
    }

    public static void main(String[] args) {
        if (args.length != 2) {
            System.err.println("Usage: java ...MaintainabilityTriageCli <java-repository-directory> <output-json-file>");
            System.exit(2);
        }

        try {
            Path repositoryRoot = Path.of(args[0]).toAbsolutePath().normalize();
            Path outputFile = Path.of(args[1]).toAbsolutePath().normalize();

            if (!Files.isDirectory(repositoryRoot)) {
                throw new IllegalArgumentException("Repository is not a directory: " + repositoryRoot);
            }

            RepositoryDetectionConfig config = new RepositoryDetectionConfig(
                    new MethodDetectionThresholds(30, 10),
                    new ClassDetectionThresholds(300, 25, 15),
                    new CohesionDetectionThresholds(0.33, 2),
                    new GodClassDetectionThresholds(47, 5, 0.33),
                    new DuplicateDetectionThresholds(10, 2),
                    new NamingDetectionConfig(true, true, true),
                    true
            );

            System.out.println("Configuration: PRELIMINARY_DEMONSTRATION_NOT_CALIBRATED");
            System.out.println("Repository: " + repositoryRoot);
            RepositoryTriageResult result = new RepositoryTriageService().analyze(repositoryRoot, config);
            Path written = new MaintainabilityEvidenceExporter().export(repositoryRoot, result, outputFile);

            System.out.println("Total Java files: " + result.analysis().totalFiles());
            System.out.println("Parsed Java files: " + result.analysis().parsedFiles());
            System.out.println("Failed Java files: " + result.analysis().failedFiles());
            System.out.println("Maintainability findings: " + result.findingCount());
            System.out.println("Related issue groups: " + result.groupCount());
            System.out.println("Evidence JSON: " + written);
            System.out.println("Result is analyzer evidence, NOT verified ground truth.");
        } catch (Exception exception) {
            System.err.println("Maintainability triage failed: " + exception.getMessage());
            exception.printStackTrace(System.err);
            System.exit(1);
        }
    }
}
