import React from 'react'
import { useTranslation } from 'react-i18next'
import { useReadmeDrawer } from './context'
import { RiBookReadLine } from '@remixicon/react'
import type { PluginDetail } from '../types'

export const ReadmeEntrance = ({
  detail,
}: {
  detail: PluginDetail
}) => {
  const { t } = useTranslation()
  const { openReadme } = useReadmeDrawer()
  const handleReadmeClick = () => {
    if (detail)
      openReadme(detail)
  }
  return (
    <div className="flex flex-col items-start justify-center gap-2 px-4 pb-4 pt-0">
      <div className="relative h-2 w-8 shrink-0">
        <div className="h-0.5 w-full bg-gradient-to-r from-transparent via-divider-regular to-transparent"></div>
      </div>

      <button
        onClick={handleReadmeClick}
        className="group flex w-full items-center justify-start gap-1 transition-opacity hover:opacity-80"
      >
        <div className="relative flex h-3 w-3 items-center justify-center overflow-hidden">
          <RiBookReadLine className="h-3 w-3 text-text-tertiary" />
        </div>
        <span className="text-xs font-normal leading-4 text-text-tertiary">
          {t('plugin.readmeInfo.needHelpCheckReadme')}
        </span>
      </button>
    </div>
  )
}
