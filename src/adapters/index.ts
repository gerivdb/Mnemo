/**
 * ECOS Adapters Index
 * 
 * Adapters for integrating MNEMO with our ECOS ecosystem:
 * - ECOS Adapter: Generic ECOS integration
 * - KIVA Adapter: KIVA-CLI specific integration
 * 
 * @date 2026-04-15
 */

export { ECOSAdapter, ECOSSession, Observation, createECOSAdapter } from './ecos';
export { KIVAAdapter, KIVASession, createKIVAAdapter } from './kiva';

/**
 * Default export - creates all adapters
 */
import { createECOSAdapter } from './ecos';
import { createKIVAAdapter } from './kiva';

export function createAllAdapters(ecosRoot?: string) {
    return {
        ecos: createECOSAdapter(ecosRoot),
        kiva: createKIVAAdapter(ecosRoot)
    };
}
