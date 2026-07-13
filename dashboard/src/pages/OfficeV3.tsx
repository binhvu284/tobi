import { lazy, Suspense, useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { getOfficeV3Config } from '../api'
import PageLoader from '../components/PageLoader'
import OfficeV3Shell from '../components/office-v3/OfficeV3Shell'

const LegacyOffice = lazy(() => import('./Office'))

/** Flagged Office replacement. `?legacy=1` is the zero-data-loss emergency fallback. */
export default function OfficeV3() {
  const [params] = useSearchParams()
  const forcedLegacy = params.get('legacy') === '1'
  const [enabled, setEnabled] = useState<boolean | null>(forcedLegacy ? false : null)

  useEffect(() => {
    if (forcedLegacy) return
    getOfficeV3Config().then(result => setEnabled(result.enabled)).catch(() => setEnabled(true))
  }, [forcedLegacy])

  if (enabled == null) return <PageLoader preset="office" />
  if (!enabled) return <Suspense fallback={<PageLoader preset="office" />}><LegacyOffice /></Suspense>
  return <OfficeV3Shell />
}
