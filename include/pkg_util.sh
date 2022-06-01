#!/bin/bash
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

pkg_warn() {
	local ret=$?
	echo "Error: $@" >&2
	return $?
}

pkg_log() {
	local ret=$?
	echo "$@" >&2
	return $ret
}

pkg_get_platform() {
	local arch=
	declare -f AskPlatform &>/dev/null || . /pkgscripts-ng/include/platforms
	declare -f AskPlatform &>/dev/null || . /pkgscripts-ng/include/check
	declare -f AskPlatform &>/dev/null || return 1

	local abbr=$(AskPlatform && echo $PLATFORM_ABBR)
	local buildTarget=$(AskPlatform && echo $BUILD_TARGET)


	if [ -z "$arch" ]; then
		case "$buildTarget" in
			BROMOLOW)		arch="bromolow" ;;
			GRANTLEY)		arch="grantley" ;;
			CEDARVIEW)		arch="cedarview" ;;
			AVOTON)			arch="avoton" ;;
			BRASWELL)		arch="braswell" ;;
			APOLLOLAKE)		arch="apollolake" ;;
			MARVELL_ARMADAXP)	arch="armadaxp" ;;
			MARVELL_ARMADA370)	arch="armada370" ;;
			MARVELL_ARMADA375)	arch="armada375" ;;
			EVANSPORT)		arch="evansport" ;;
			MINDSPEED_COMCERTO2K)	arch="comcerto2k" ;;
			ALPINE)			arch="alpine" ;;
			STM_MONACO)             arch="monaco" ;;
			BROADWELL)		arch="broadwell" ;;
			BROADWELLNK)		arch="broadwellnk" ;;
			KVMX64)			arch="kvmx64" ;;
			MARVELL_ARMADA38X)      arch="armada38x" ;;
			REALTEK_RTD1296)        arch="rtd1296" ;;
			DENVERTON)		arch="denverton" ;;
			MARVELL_ARMADA37XX)     arch="armada37xx" ;;
			PURLEY)               	arch="purley" ;;
			GEMINILAKE)		arch="geminilake" ;;
			V1000)                  arch="v1000" ;;
			EPYC7002)		arch="epyc7002" ;;
			R1000)			arch="r1000" ;;
			BROADWELLNKV2)		arch="broadwellnkv2" ;;
			REALTEK_RTD1619B)	arch="rtd1619b" ;;
			*)			arch="" ;;
		esac
	fi

	[ -z "$arch" ] && { echo "[ERROR] cannot get platform arch" && exit 1; }
	echo "$arch"
}

plat_to_family() {
	local plat="$1"
	local family=

	case "$plat" in
		bromolow | cedarview | avoton | braswell | apollolake | grantley | broadwell | kvmx64 | denverton | broadwellnk  | purley | geminilake | v1000 | r1000 | broadwellnkv2 | epyc7002)
			family="x86_64"
			;;
		evansport )
			family="i686"
			;;
		alpine | alpine4k )
			family="armv7"
			;;
		rtd1296 | armada37xx | rtd1619b)
			family="armv8"
			;;
		# armv7 not ready platforms.
		comcerto2k | armada370 | armada375 | armadaxp | monaco | armada38x | rtd1296 )
			family="$plat"
			;;
		*)
			echo "Failed to get platform family for $family" 1>&2
			echo "Please add the mapping information into pkgscripts-ng/include/pkg_util.sh:pkg_get_platform_family" 1>&2
			return 1
	esac
	echo "$family"
	return 0
}

pkg_get_platform_family() {
	local plat=$(pkg_get_platform) || return 1

	plat_to_family "$plat"
}

pkg_get_spk_platform() {
	local plat=$(pkg_get_platform) || return 1
	echo "$plat"
}

# Run *.sh under $1 to create scripts; e.g. scripts or WIZARD_UIFILES
pkg_create_scripts() {
	[ ! -d "$1" ] && return
	local exe= prefix= list=
	cd $1
	for exe in `ls *.sh`; do
		sh $exe
		prefix=`echo $exe | sed 's/.sh$//'`
		list="$list $1/$prefix $1/${prefix}_*"
	done
	cd - > /dev/null
	echo "$list"
}

check_bash_ver_ge_4() {
	if [ ${BASH_VERSION:0:1} -ge 4 ]; then
		return 1
	else
		return 0
	fi
}

check_deprecate() {
	declare -A key_map=(["os_min_ver"]="firmware")
	local key=$1
	# Check whether necessary have deprecated key
	case $key in
		os_min_ver)
			echo "Warning: Exist deprecated key \"${key_map[$key]}\" for \"$key\" after version 6.1-14715" >&2
			deprecate_key=${key_map[$key]}
			return 1
			;;
		*) return 0
	esac
}

check_necessary_field() {
	# $1: necessary keys in map structure
	# $2: retrieved keys in map structure
	local -n nec_map=$1
	local -n key_map=$2

	for key in ${!nec_map[@]}; do
		if [ ${nec_map[$key]} -eq 0 ]; then
			if [ ! -z ${!key+x} ]; then
				# necessary fields are not defined in INFO.sh
				# e.g. maintainer in pkg_init_info
				echo "$key=\"${!key}\""
			else
				check_deprecate $key
				local ret_val=$?
				if [ $ret_val -eq 0 ]; then
					echo "Error: Found unspecified necessary field \"$key\" without deprecated key" >&2
				else
					local deprecate_is_written=false
					for key_read in ${!key_map[@]}; do
						# Check whether we have retrieved keys that are deprecated keys
						if [ $key_read == $deprecate_key ] && [ ! -z ${!key_read+x} ]; then
							deprecate_is_written=true
							echo "Warning: Found specified deprecated key for \"$key\"" >&2
							break
						fi
					done
					if ! $deprecate_is_written; then
						echo "Error: Found unspecified necessary field \"$key\" without specified deprecated key" >&2
					fi
				fi
			fi
		fi
	done
}

pkg_dump_info() {
	local langs="enu cht chs krn ger fre ita spn jpn dan nor sve nld rus plk ptb ptg hun trk csy"
	local fields="package version maintainer maintainer_url distributor distributor_url arch exclude_arch model exclude_model
		adminprotocol adminurl adminport firmware dsmuidir dsmappname dsmapppage dsmapplaunchname checkport allow_altport
		startable helpurl report_url support_center install_reboot install_dep_packages install_conflict_packages install_dep_services
		instuninst_restart_services startstop_restart_services start_dep_services silent_install silent_upgrade silent_uninstall install_type
		checksum package_icon package_icon_120 package_icon_128 package_icon_144 package_icon_256 thirdparty support_conf_folder
		auto_upgrade_from offline_install precheckstartstop os_min_ver os_max_ver beta ctl_stop ctl_install ctl_uninstall
		install_break_packages install_replace_packages use_deprecated_replace_mechanism description displayname"
	local f=

	for f in $fields; do
		if [ -n "${!f}" ]; then
			echo $f=\"${!f}\"
		fi
	done

	for lang in $langs; do
		description="description_${lang}"
		if [ -n "${!description}" ]; then
			echo "${description}=\"${!description}\""
		fi
		displayname="displayname_${lang}"
		if [ -n "${!displayname}" ]; then
			echo "${displayname}=\"${!displayname}\""
		fi
	done
}

pkg_make_package() { # <source path> <dest path>
	local source_path=$1
	local dest_path=$2
	local package_name="package.tgz"
	local temp_extractsize="extractsize_tmp"
	local pkg_size=
	local tar_option="cJf"

	# check parameters
	if [ -z "$source_path" -o ! -d "$source_path" ]; then
		pkg_warn "pkg_make_package: bad parameters, please set source dir"
		return 1
	fi
	if [ -z "$dest_path"  -o ! -d "$dest_path" ]; then
		pkg_warn "pkg_make_package: bad parameters, please set destination dir"
		return 1
	fi

	# add extractsize to INFO
	pkg_size=`du -sk "$source_path" | awk '{print $1}'`
	echo "${pkg_size}" >> "$dest_path/$temp_extractsize"
	echo ls $source_path \| tar $tar_option "$dest_path/$package_name" -C "$source_path" -T /dev/stdin
	ls $source_path | tar $tar_option "$dest_path/$package_name" -C "$source_path" -T /dev/stdin
}

__get_spk_name() { #<info path>
	local spk_name=
	local platform_func="$1"
	local info_path="${2:-$PKG_DIR/INFO}"
	local package_name="$3"

	. $info_path

	# construct package name
	if [ -z "$package" -o -z "$arch" -o -z "$version" ]; then
		pkg_warn "pkg_make_spk: package, arch, version can not be empty"
		return 1
	fi

	if [ "x$arch" = "xnoarch" ]; then
		spk_arch="noarch"
	elif ! spk_arch=$($platform_func); then
		spk_arch="none"
	fi

	if [ "x$arch" = "xnoarch" ]; then
		spk_arch=""
	else
		spk_arch="-"$spk_arch
	fi

	if [ -z "$package_name" ]; then
		package_name="$package";
	fi

	if [ "${NOSTRIP}" == NOSTRIP ]; then
		spk_name="$package_name$spk_arch-${version}_debug.spk"
	else
		spk_name="$package_name$spk_arch-$version.spk"
	fi
	echo $spk_name;
}

pkg_get_spk_name() { #<info path> [package name]
	__get_spk_name pkg_get_spk_platform $@
}

pkg_get_spk_family_name() { #<info path> [package name]
	__get_spk_name pkg_get_platform_family $@
}

pkg_make_spk() { # <source path> <dest path> <spk file name>
	local pack="tar cf"
	local source_path=$1
	local dest_path=$2
	local info_path="$source_path/INFO"
	local spk_name=$3
	local spk_arch=
	local temp_extractsize="extractsize_tmp"

	# check parameters
	if [ -z "$source_path" -o ! -d "$source_path" ]; then
		pkg_warn "pkg_make_spk: bad parameters, please set source dir"
		return 1
	fi
	if [ -z "$dest_path"  -o ! -d "$dest_path" ]; then
		pkg_warn "pkg_make_spk: bad parameters, please set destination dir"
		return 1
	fi

	# check INFO exists and source INFO
	if [ ! -r "$info_path" ]; then
		pkg_warn "pkg_make_spk: INFO '$info_path' is not existed"
		return 1
	fi
	spk_name=${3:-`pkg_get_spk_name $info_path`}
	# add extractsize to INFO
	pkg_size=`cat $source_path/$temp_extractsize`
	echo "extractsize=\"${pkg_size}\"" >> $info_path
	rm "$source_path/$temp_extractsize"

	echo "toolkit_version=\"$DSM_BUILD_NUM\"" >> $info_path
	echo "create_time=\"$(date +%Y%m%d-%T)\"" >> $info_path

	# tar .spk file
	pkg_log "creating package: $spk_name"
	pkg_log "source:           $source_path"
	pkg_log "destination:      $dest_path/$spk_name"
	$pack "$dest_path/$spk_name" -C "$source_path" $(ls $source_path)
}

[ "$(caller)" != "0 NULL" ] && return 0

usage() {
	cat >&2 <<EOF
USAGE: $(basename $0) <action> [action options...]
ACTION:
	make_spk <source path> <dest path> <spk name>
	make_package <source path> <dest path>
EOF
	exit 0
}

[ $# -eq 0 ] && usage
PkgBuildAction=$1 ; shift
case "$PkgBuildAction" in
	make_spk)	pkg_make_spk "$@" ;;
	make_package)	pkg_make_package "$@" ;;
	*)		usage ;;
esac
