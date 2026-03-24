################################################################################################
# fastfetch "About Me" workstation status

alias about="fastfetch -c ~/.config/fastfetch/custom_ff.json"


################################################################################################
# OpenVPN aliases 

alias vpnstart='openvpn3 session-start --config OpenVPN_Connect'
alias vpnstatus='openvpn3 sessions-list'
alias vpnconfig='openvpn3 configs-list'
alias vpnstop='openvpn3 session-manage --config OpenVPN_Connect --disconnect'



################################################################################################
# Command shortcut aliases 

alias awslogin="aws sso login --sso-session awsorg"
alias awsprofiles="aws configure list-profiles | /usr/bin/sort"
alias bastion="~/bin/bastion.py"
alias diff="/var/lib/snapd/snap/bin/difftastic"
alias dkps="/usr/bin/docker ps -a"
alias la="/usr/bin/lsd -al"
alias ll="/usr/bin/lsd -l"
alias ls="/usr/bin/lsd"
alias ltr="/usr/bin/lsd -ltr"
alias lzd="/home/linuxbrew/.linuxbrew/bin/lazydocker"
alias top="/usr/bin/btop"


################################################################################################
# Command shortcut functions

awsid() {
    aws sts get-caller-identity --profile ${1} --query Account --output text
}

awsnewprofile() {
    aws configure sso --profile ${1}
}

awsregion() {
    aws configure get region --profile ${1}
}

awssts() {
    if [ -z "$1" ]; then
        aws sts get-caller-identity
    else
        aws sts get-caller-identity --profile "$1"
    fi
}

dkexec() {
    docker exec -it ${1} /bin/bash
}

mksnap() {
    TIMESTAMP=$(date +'%Y%m%d_%H%M%S')
    for i in root home
        do sudo snapper -c ${i} create -d "Manual_Snapshot_${TIMESTAMP}"
    done
}

lssnap() {
    for i in root home
        do sudo snapper -c ${i} list
    done
}
