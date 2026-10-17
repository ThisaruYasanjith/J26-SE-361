
package lk.sliit.codecleanliness.detection;

/**
 * Explicit, preliminary naming-convention configuration.
 *
 * The first implementation supports conventional Java
 * class, method and field naming.
 */
public record NamingDetectionConfig(
        boolean checkTypes,
        boolean checkMethods,
        boolean checkFields
) {
    public NamingDetectionConfig {
        if (!checkTypes && !checkMethods && !checkFields) {
            throw new IllegalArgumentException(
                    "At least one naming check must be enabled"
            );
        }
    }
}
