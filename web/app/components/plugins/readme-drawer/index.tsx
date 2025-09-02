'use client'
import React from 'react'
import type { FC } from 'react'
import { useTranslation } from 'react-i18next'
import { RiBookReadLine, RiCloseLine } from '@remixicon/react'
import cn from '@/utils/classnames'
import Drawer from '@/app/components/base/drawer'
import { Markdown } from '@/app/components/base/markdown'
import { usePluginReadme } from '@/service/use-plugins'
// import type { PluginDetail } from '@/app/components/plugins/types'
import Loading from '@/app/components/base/loading'
import { useLanguage } from '@/app/components/header/account-setting/model-provider-page/hooks'
import PluginTitleInfo from '@/app/components/plugins/plugin-title-info'
import Modal from '@/app/components/base/modal'
import { useReadmeDrawer } from './context'

// type ReadmeDrawerProps = {
//   showType: 'drawer' | 'modal'
//   detail?: PluginDetail
//   onClose: () => void
// }

const ReadmeDrawer: FC = () => {
  // console.log('detail', detail)
  const { currentDetailInfo, closeReadme: onClose } = useReadmeDrawer()
  const detail = currentDetailInfo?.detail
  const showType = currentDetailInfo?.showType
  const { t } = useTranslation()
  const language = useLanguage()

  // 获取插件的唯一标识符用于获取 README
  const pluginUniqueIdentifier = detail?.plugin_unique_identifier || ''

  // 根据语言设置调用 usePluginReadme，非中文时传递 language 参数
  const readmeLanguage = language === 'zh-Hans' ? undefined : 'en'
  const { data: readmeData, isLoading, error } = usePluginReadme(
    pluginUniqueIdentifier,
    readmeLanguage,
  )

  if (!detail) return null

  const children = (
    <div className="flex h-full w-full flex-col overflow-hidden">
      {/* Header */}
      <div className="bg-background-body px-4 py-4">
        {/* Title Bar */}
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-1">
            <RiBookReadLine className="h-3 w-3 text-text-tertiary" />
            <span className="text-xs font-medium uppercase text-text-tertiary">
              {t('plugin.readmeInfo.title')}
            </span>
          </div>
          <button
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-state-base-hover"
          >
            <RiCloseLine className="h-4 w-4 text-text-tertiary" />
          </button>
        </div>

        <PluginTitleInfo detail={detail} size="large" />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        {(() => {
          if (isLoading) {
            return (
              <div className="flex h-40 items-center justify-center">
                <Loading type="area" />
              </div>
            )
          }

          if (error) {
            return (
              <div className="py-8 text-center text-text-tertiary">
                <p>{t('plugin.readmeInfo.noReadmeAvailable')}</p>
              </div>
            )
          }

          if (readmeData?.readme) {
            return (
              <Markdown
                content={readmeData.readme}
                className="prose-sm prose max-w-none"
              />
            )
          }

          return (
            <div className="py-8 text-center text-text-tertiary">
              <p>{t('plugin.readmeInfo.noReadmeAvailable')}</p>
            </div>
          )
        })()}
      </div>
    </div>
  )

  return (
    showType === 'drawer' ? (
      <Drawer
        isOpen={!!detail}
        onClose={onClose}
        footer={null}
        mask={true}
        positionCenter={false}
        showClose={false}
        panelClassName={cn(
          'mb-2 ml-2 mt-16 !w-[600px] !max-w-[600px] justify-start rounded-2xl border-[0.5px] border-components-panel-border !bg-components-panel-bg !p-0 shadow-xl',
          '!z-[9999]', // 最高层级
        )}
        dialogClassName={cn(
          '!z-[9998]',
          '!flex !items-start !justify-start', // 从左侧弹出
        )}
      >
        {children}
      </Drawer>
    ) : (
      <Modal
        isShow={!!detail}
        onClose={onClose}
      >
        {children}
      </Modal>
    )
  )
}

export default ReadmeDrawer
